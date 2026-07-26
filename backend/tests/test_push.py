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
