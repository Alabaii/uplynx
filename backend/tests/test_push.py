from sqlalchemy import select

from app.core.config import get_settings
from app.models import PushSubscription


def enable_push(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")


def test_push_config_disabled_without_keys(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", None)
    monkeypatch.setattr(settings, "vapid_private_key", None)
    response = client.get("/api/v1/push/config")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "public_key": None}


def test_push_config_enabled_with_keys(client, monkeypatch):
    enable_push(monkeypatch)
    response = client.get("/api/v1/push/config")
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "public_key": "test-public-key"}


def test_subscribe_returns_404_when_push_disabled(client, auth_headers):
    payload = {"endpoint": "https://push.example/e1", "keys": {"p256dh": "p", "auth": "a"}}
    assert client.post("/api/v1/push/subscribe", json=payload, headers=auth_headers).status_code == 404


def test_subscribe_requires_auth(client, monkeypatch):
    enable_push(monkeypatch)
    payload = {"endpoint": "https://push.example/e1", "keys": {"p256dh": "p", "auth": "a"}}
    assert client.post("/api/v1/push/subscribe", json=payload).status_code == 401


def test_subscribe_rejects_internal_endpoints(client, auth_headers, monkeypatch):
    # адрес push-сервиса задаёт клиент, а POST по нему шлёт воркер изнутри сети
    enable_push(monkeypatch)
    for endpoint in (
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/api/v1/monitors",
        "http://localhost/hook",
        "http://[::ffff:127.0.0.1]/hook",
        "file:///etc/passwd",
    ):
        response = client.post(
            "/api/v1/push/subscribe",
            json={"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}},
            headers=auth_headers,
        )
        assert response.status_code == 400, endpoint


def test_subscribe_allows_internal_endpoints_on_prem(client, auth_headers, monkeypatch):
    # on-prem: ALLOW_PRIVATE_TARGETS снимает ограничение, как и для мониторов
    enable_push(monkeypatch)
    monkeypatch.setattr(get_settings(), "allow_private_targets", True)
    response = client.post(
        "/api/v1/push/subscribe",
        json={"endpoint": "http://127.0.0.1:9000/push", "keys": {"p256dh": "p", "auth": "a"}},
        headers=auth_headers,
    )
    assert response.status_code == 204


def test_subscribe_upsert_and_unsubscribe(client, auth_headers, db_session_factory, monkeypatch):
    enable_push(monkeypatch)
    payload = {"endpoint": "https://push.example/e1", "keys": {"p256dh": "p1", "auth": "a1"}}
    assert client.post("/api/v1/push/subscribe", json=payload, headers=auth_headers).status_code == 204

    # повторная подписка тем же endpoint — upsert: без дубликата, ключи обновлены
    payload["keys"] = {"p256dh": "p2", "auth": "a2"}
    assert client.post("/api/v1/push/subscribe", json=payload, headers=auth_headers).status_code == 204

    with db_session_factory() as db:
        subscriptions = db.scalars(select(PushSubscription)).all()
        assert len(subscriptions) == 1
        assert subscriptions[0].p256dh == "p2"
        assert subscriptions[0].auth == "a2"

    response = client.post(
        "/api/v1/push/unsubscribe", json={"endpoint": "https://push.example/e1"}, headers=auth_headers
    )
    assert response.status_code == 204
    with db_session_factory() as db:
        assert db.scalars(select(PushSubscription)).all() == []


def test_subscription_belongs_to_organization_not_device(client, db_session_factory, monkeypatch):
    """Одно устройство в двух воркспейсах — две подписки, а не конфликт.

    Таблица закрыта RLS по org_id: подписку другой организации запрос не видит,
    поэтому при глобальной уникальности endpoint вторая подписка падала с 500
    (существующая строка невидима, вставка упирается в констрейнт).
    """
    enable_push(monkeypatch)
    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")
    credentials = {"email": "owner@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=credentials)
    headers = {
        "Authorization": f"Bearer {client.post('/api/v1/auth/login', json=credentials).json()['access_token']}"
    }
    first_org = client.get("/api/v1/auth/me", headers=headers).json()["organization"]["id"]
    device = {"endpoint": "https://push.example/device", "keys": {"p256dh": "p", "auth": "a"}}
    assert client.post("/api/v1/push/subscribe", json=device, headers=headers).status_code == 204

    second = client.post("/api/v1/orgs", json={"name": "Second", "slug": "second"}, headers=headers)
    assert second.status_code == 201
    second_org = second.json()["id"]
    switched = client.post(f"/api/v1/orgs/{second_org}/switch", json={}, headers=headers)
    second_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}

    assert client.post("/api/v1/push/subscribe", json=device, headers=second_headers).status_code == 204

    with db_session_factory() as db:
        rows = db.scalars(select(PushSubscription)).all()
        assert len(rows) == 2
        assert {row.org_id for row in rows} == {first_org, second_org}

    # отписка касается только текущего воркспейса
    assert (
        client.post("/api/v1/push/unsubscribe", json={"endpoint": device["endpoint"]}, headers=second_headers).status_code
        == 204
    )
    with db_session_factory() as db:
        remaining = db.scalars(select(PushSubscription)).all()
        assert [row.org_id for row in remaining] == [first_org]


# --- пиннинг адреса при отправке (DNS rebinding) ------------------------------------------------


def _subscription(endpoint="https://push.example.com/abc"):
    return PushSubscription(org_id=1, user_id=1, endpoint=endpoint, p256dh="k", auth="a")


def test_send_web_push_pins_connection_to_verified_address(monkeypatch):
    """Соединение идёт на проверенный адрес, а не на тот, что отдаст DNS второй раз."""
    from app.services import webpush

    monkeypatch.setattr(webpush, "resolve_public_address", lambda *a, **kw: "93.184.216.34")

    captured = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(webpush, "webpush", fake_webpush)
    assert webpush.send_web_push(_subscription(), "t", "b") is True

    session = captured["requests_session"]
    assert session is not None
    # адаптер https подменён на пиннингованный, адрес зашит в замыкание
    adapter = session.get_adapter("https://push.example.com/abc")
    pool_classes = adapter.poolmanager.pool_classes_by_scheme
    connection_cls = pool_classes["https"].ConnectionCls
    assert connection_cls.__name__ == "_PinnedConnection"


def test_send_web_push_refuses_endpoint_that_became_internal(monkeypatch):
    """Если имя стало резолвиться во внутренний адрес — отправки не происходит вовсе."""
    from app.core.ssrf import BlockedTargetError
    from app.services import webpush

    def blocked(*_args, **_kwargs):
        raise BlockedTargetError("target resolves to non-public address 169.254.169.254")

    monkeypatch.setattr(webpush, "resolve_public_address", blocked)

    called = []
    monkeypatch.setattr(webpush, "webpush", lambda **kw: called.append(kw))

    assert webpush.send_web_push(_subscription(), "t", "b") is False
    assert called == []


def test_send_web_push_skips_pinning_on_prem(monkeypatch):
    """allow_private_targets: resolve_public_address отдаёт None — пиннинг не нужен."""
    from app.services import webpush

    monkeypatch.setattr(webpush, "resolve_public_address", lambda *a, **kw: None)

    captured = {}
    monkeypatch.setattr(webpush, "webpush", lambda **kw: captured.update(kw))

    assert webpush.send_web_push(_subscription("https://internal.lan/p"), "t", "b") is True
    assert captured["requests_session"] is None


def test_pinned_session_ignores_environment_proxy(monkeypatch):
    """С HTTPS_PROXY в окружении requests пошёл бы в прокси, а имя резолвил бы он.

    Тогда проверенный адрес перестаёт что-либо значить и окно rebinding
    открывается заново — поэтому пиннингованная сессия ходит напрямую.
    """
    from app.services.webpush import pinned_session

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    session = pinned_session("93.184.216.34")

    assert session.trust_env is False
    # именно trust_env отвечает за подхват прокси из окружения при отправке
    assert session.rebuild_proxies(type("R", (), {"url": "https://push.example.com/x", "headers": {}})(), {}) == {}
