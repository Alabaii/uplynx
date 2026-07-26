from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import CheckResult, Monitor, Organization, User


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def enable_status_page(client, headers):
    response = client.patch("/api/v1/orgs/current", json={"status_page_enabled": True}, headers=headers)
    assert response.status_code == 200
    return response


def seed_monitor(db, slug, status="up", enabled=True, name=None):
    user = db.scalar(select(User).order_by(User.id).limit(1))
    org = db.scalar(select(Organization).where(Organization.slug == "default"))
    monitor = Monitor(
        user_id=user.id,
        org_id=org.id,
        slug=slug,
        name=name or slug.title(),
        type="http",
        status=status,
        url=f"https://{slug}.example.com",
        interval=60,
        config_json={},
        enabled=enabled,
    )
    db.add(monitor)
    db.flush()
    return monitor.id


def test_status_page_404_when_disabled_or_unknown_slug(client, auth_headers):
    # страница выключена (default после регистрации) — 404, как и несуществующий slug
    assert client.get("/api/v1/status/default").status_code == 404
    assert client.get("/api/v1/status/no-such-org").status_code == 404


def test_status_page_shows_only_enabled_monitors_without_sensitive_fields(client, auth_headers, db_session_factory):
    enable_status_page(client, auth_headers)
    with db_session_factory() as db:
        visible_id = seed_monitor(db, "site", status="up")
        seed_monitor(db, "hidden", status="down", enabled=False)
        now = datetime.now(timezone.utc)
        db.add(CheckResult(monitor_id=visible_id, task_id="t1", status="up", response_time_ms=100, details={}, timestamp=now - timedelta(minutes=2)))
        db.add(CheckResult(monitor_id=visible_id, task_id="t2", status="down", response_time_ms=None, details={}, timestamp=now - timedelta(minutes=1)))
        db.commit()

    response = client.get("/api/v1/status/default")
    assert response.status_code == 200
    body = response.json()

    assert body["organization"] == "My team"
    assert body["overall"] == "operational"
    assert body["updated_at"] is not None
    assert len(body["monitors"]) == 1

    monitor = body["monitors"][0]
    # только имя, статус, uptime, last_check и флаг обслуживания — ничего чувствительного
    assert set(monitor) == {"name", "status", "uptime_pct", "last_check_at", "in_maintenance"}
    assert monitor["name"] == "Site"
    assert monitor["status"] == "up"
    assert monitor["uptime_pct"] == 50.0  # 1 из 2 за 24 часа
    assert monitor["last_check_at"] is not None


def test_status_page_uptime_null_without_checks(client, auth_headers, db_session_factory):
    enable_status_page(client, auth_headers)
    with db_session_factory() as db:
        seed_monitor(db, "fresh", status="pending")
        db.commit()

    monitor = client.get("/api/v1/status/default").json()["monitors"][0]
    assert monitor["uptime_pct"] is None
    assert monitor["last_check_at"] is None


def fetch_status_fresh(client):
    """Страница кэшируется на 15 секунд — в тестах про пересчёт кэш сбрасываем явно."""
    from app.api.v1.endpoints.status import _cache

    _cache.clear()
    return client.get("/api/v1/status/default").json()


def test_status_page_overall_priority(client, auth_headers, db_session_factory):
    enable_status_page(client, auth_headers)
    with db_session_factory() as db:
        seed_monitor(db, "ok", status="up")
        seed_monitor(db, "warmup", status="pending")
        db.commit()
    # up + pending: pending игнорируется
    assert fetch_status_fresh(client)["overall"] == "operational"

    with db_session_factory() as db:
        seed_monitor(db, "slow", status="degraded")
        db.commit()
    assert fetch_status_fresh(client)["overall"] == "degraded"

    with db_session_factory() as db:
        seed_monitor(db, "broken", status="down")
        db.commit()
    # down приоритетнее degraded
    assert fetch_status_fresh(client)["overall"] == "down"


def test_status_page_toggle_owner_only_and_audited(client):
    owner = register_and_login(client, "owner@example.com")
    admin = register_and_login(client, "admin@example.com")
    admin_id = client.get("/api/v1/auth/me", headers=admin).json()["id"]
    assert (
        client.patch(f"/api/v1/orgs/current/members/{admin_id}", json={"role": "admin"}, headers=owner).status_code
        == 200
    )

    # admin недостаточно — только owner
    denied = client.patch("/api/v1/orgs/current", json={"status_page_enabled": True}, headers=admin)
    assert denied.status_code == 403
    assert client.get("/api/v1/status/default").status_code == 404

    enabled = enable_status_page(client, owner)
    assert enabled.json()["status_page_enabled"] is True
    assert client.get("/api/v1/status/default").status_code == 200

    # изменение попало в аудит-лог
    events = client.get("/api/v1/orgs/current/audit", headers=owner).json()
    org_updates = [event for event in events if event["action"] == "org.update"]
    assert org_updates and "status_page_enabled" in org_updates[0]["payload"]["changes"]

    # выключение возвращает 404
    disabled = client.patch("/api/v1/orgs/current", json={"status_page_enabled": False}, headers=owner)
    assert disabled.status_code == 200
    assert disabled.json()["status_page_enabled"] is False
    assert client.get("/api/v1/status/default").status_code == 404


def test_me_returns_status_page_enabled(client, auth_headers):
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["organization"]["status_page_enabled"] is False
    enable_status_page(client, auth_headers)
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["organization"]["status_page_enabled"] is True


def test_status_page_is_cached_briefly(client, auth_headers, monkeypatch):
    from app.api.v1.endpoints import status as status_endpoint

    status_endpoint._cache.clear()
    client.patch("/api/v1/orgs/current", json={"status_page_enabled": True}, headers=auth_headers)
    client.post(
        "/api/v1/monitors",
        json={"id": "first", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )

    first = client.get("/api/v1/status/default")
    assert first.status_code == 200
    assert first.headers["Cache-Control"] == "public, max-age=15"
    assert [m["name"] for m in first.json()["monitors"]] == ["first"]

    # монитор добавлен, но пока кэш жив — страница отдаёт прежний снимок
    client.post(
        "/api/v1/monitors",
        json={"id": "second", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    assert [m["name"] for m in client.get("/api/v1/status/default").json()["monitors"]] == ["first"]

    # по истечении TTL пересчитывается
    status_endpoint._cache.clear()
    assert [m["name"] for m in client.get("/api/v1/status/default").json()["monitors"]] == ["first", "second"]


def test_disabled_status_page_is_not_served_from_cache(client, auth_headers):
    from app.api.v1.endpoints import status as status_endpoint

    status_endpoint._cache.clear()
    client.patch("/api/v1/orgs/current", json={"status_page_enabled": True}, headers=auth_headers)
    assert client.get("/api/v1/status/default").status_code == 200

    # выключение страницы срабатывает сразу, а не по истечении TTL кэша
    client.patch("/api/v1/orgs/current", json={"status_page_enabled": False}, headers=auth_headers)
    assert client.get("/api/v1/status/default").status_code == 404
