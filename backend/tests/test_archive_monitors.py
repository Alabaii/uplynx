from sqlalchemy import select

from app.models import CheckResult, Monitor

MONITOR = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_archived_monitor_disappears_from_product(client, auth_headers):
    client.post("/api/v1/monitors", json=MONITOR, headers=auth_headers)
    assert [m["id"] for m in client.get("/api/v1/monitors", headers=auth_headers).json()] == ["site"]

    assert client.delete("/api/v1/monitors/site", headers=auth_headers).status_code == 204

    assert client.get("/api/v1/monitors", headers=auth_headers).json() == []
    assert client.get("/api/v1/monitors/site", headers=auth_headers).status_code == 404
    assert client.get("/api/v1/monitors/uptime", headers=auth_headers).json() == []


def test_archive_keeps_row_and_history(client, auth_headers, db_session_factory):
    client.post("/api/v1/monitors", json=MONITOR, headers=auth_headers)
    with db_session_factory() as db:
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        db.add(CheckResult(monitor_id=monitor.id, task_id="kept", status="up", details={}))
        db.commit()
        monitor_id = monitor.id

    client.delete("/api/v1/monitors/site", headers=auth_headers)

    with db_session_factory() as db:
        archived = db.get(Monitor, monitor_id)
        # строка и история остаются: удаление восстановимо и не рвёт внешние ключи
        assert archived is not None
        assert archived.archived_at is not None
        assert archived.enabled is False
        assert archived.next_run_at is None
        assert db.scalar(select(CheckResult).where(CheckResult.task_id == "kept")) is not None

    # но в истории организации архивный монитор больше не показывается
    assert client.get("/api/v1/history", headers=auth_headers).json() == []


def test_archive_frees_the_slug(client, auth_headers, db_session_factory):
    client.post("/api/v1/monitors", json=MONITOR, headers=auth_headers)
    client.delete("/api/v1/monitors/site", headers=auth_headers)

    # тот же id можно занять заново — раньше слаг оставался занят навсегда
    recreated = client.post("/api/v1/monitors", json={**MONITOR, "url": "https://new.example"}, headers=auth_headers)
    assert recreated.status_code == 201
    assert recreated.json()["url"] == "https://new.example"

    with db_session_factory() as db:
        rows = db.scalars(select(Monitor).where(Monitor.slug == "site")).all()
        assert len(rows) == 2
        assert sorted(row.archived_at is None for row in rows) == [False, True]


def test_archived_monitor_not_resurrected_by_config_sync(client, auth_headers):
    client.post("/api/v1/monitors", json=MONITOR, headers=auth_headers)
    client.delete("/api/v1/monitors/site", headers=auth_headers)

    # выгруженный конфиг не содержит архивный монитор...
    config = client.get("/api/v1/config", headers=auth_headers).json()
    assert "site" not in config["content"]

    # ...и загрузка конфига с другим монитором его не воскрешает
    upload = client.post(
        "/api/v1/config",
        json={"content": "version: 1\nmonitors:\n  - id: other\n    type: http\n    url: https://other.example\n    interval: 60\n", "format": "yaml"},
        headers=auth_headers,
    )
    assert upload.status_code == 200
    assert [m["id"] for m in client.get("/api/v1/monitors", headers=auth_headers).json()] == ["other"]


def test_same_slug_allowed_in_two_organizations(client, monkeypatch, db_session_factory):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")
    owner = register_and_login(client, "owner@example.com")
    # в enterprise действует гейтинг тарифа: free разрешает http не чаще 300с
    monitor = {**MONITOR, "interval": 300}

    assert client.post("/api/v1/monitors", json=monitor, headers=owner).status_code == 201

    created = client.post("/api/v1/orgs", json={"name": "Second", "slug": "second"}, headers=owner)
    switched = client.post(f"/api/v1/orgs/{created.json()['id']}/switch", headers=owner)
    second = {"Authorization": f"Bearer {switched.json()['access_token']}"}

    # раньше здесь падал IntegrityError (уникальность была по user_id+slug) → 500
    second_monitor = client.post("/api/v1/monitors", json=monitor, headers=second)
    assert second_monitor.status_code == 201

    with db_session_factory() as db:
        assert len(db.scalars(select(Monitor).where(Monitor.slug == "site")).all()) == 2


def test_duplicate_slug_in_same_org_still_conflicts(client, auth_headers):
    assert client.post("/api/v1/monitors", json=MONITOR, headers=auth_headers).status_code == 201
    assert client.post("/api/v1/monitors", json=MONITOR, headers=auth_headers).status_code == 409
