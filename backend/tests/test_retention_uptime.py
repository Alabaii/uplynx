from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import CheckResult, Monitor, Organization, UptimeDaily, User
from app.services.retention import ensure_partitions, rollup_and_prune

MONITOR_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def seed_monitor(db, slug="site"):
    user = User(email=f"{slug}@example.com", hashed_password="x")
    org = Organization(name="My team", slug="default")
    db.add_all([user, org])
    db.flush()
    monitor = Monitor(
        user_id=user.id,
        org_id=org.id,
        slug=slug,
        name="Site",
        type="http",
        status="up",
        url="https://example.com",
        interval=60,
        config_json={},
        enabled=True,
    )
    db.add(monitor)
    db.flush()
    return monitor.id, org.id


def add_result(db, monitor_id, status, response_ms, timestamp, task_id):
    db.add(
        CheckResult(
            monitor_id=monitor_id,
            task_id=task_id,
            status=status,
            response_time_ms=response_ms,
            details={},
            timestamp=timestamp,
        )
    )


def test_rollup_and_prune_archives_old_and_keeps_fresh(db_session_factory):
    retention_days = get_settings().retention_days
    with db_session_factory() as db:
        monitor_id, org_id = seed_monitor(db)
        # старый день целиком за границей ретеншена, полдень — чтобы не пересекать границу суток
        old_base = (datetime.now(timezone.utc) - timedelta(days=retention_days + 1)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        add_result(db, monitor_id, "up", 100, old_base, "old-1")
        add_result(db, monitor_id, "up", 200, old_base + timedelta(minutes=1), "old-2")
        add_result(db, monitor_id, "degraded", 300, old_base + timedelta(minutes=2), "old-3")
        add_result(db, monitor_id, "down", None, old_base + timedelta(minutes=3), "old-4")
        fresh_at = datetime.now(timezone.utc)
        add_result(db, monitor_id, "up", 50, fresh_at, "fresh-1")
        db.commit()

        assert rollup_and_prune(db) == (1, 4)

        daily = db.scalars(select(UptimeDaily)).all()
        assert len(daily) == 1
        row = daily[0]
        assert row.org_id == org_id
        assert row.monitor_id == monitor_id
        assert row.date == old_base.date()
        assert row.checks_total == 4
        assert row.checks_up == 2
        assert row.checks_degraded == 1
        assert row.checks_down == 1
        assert row.avg_response_ms == 200  # (100 + 200 + 300) / 3, NULL не учитывается

        # свежие строки целы, старые удалены
        remaining = db.scalars(select(CheckResult.task_id)).all()
        assert remaining == ["fresh-1"]

        # повторный вызов идемпотентен: ничего не дублирует и не меняет
        assert rollup_and_prune(db) == (0, 0)
        assert db.scalar(select(func.count()).select_from(UptimeDaily)) == 1
        assert db.scalar(select(UptimeDaily)).checks_total == 4


def test_ensure_partitions_noop_on_sqlite(db_session_factory):
    # партиционирование только для postgres; на sqlite вызов безопасен и ничего не делает
    with db_session_factory() as db:
        assert ensure_partitions(db) is None


def test_monitors_uptime_math_and_empty_monitor(client, auth_headers, db_session_factory):
    for monitor_id in ("site", "empty"):
        response = client.post(
            "/api/v1/monitors",
            json={**MONITOR_PAYLOAD, "id": monitor_id},
            headers=auth_headers,
        )
        assert response.status_code == 201

    with db_session_factory() as db:
        internal_id = db.scalar(select(Monitor.id).where(Monitor.slug == "site"))
        now = datetime.now(timezone.utc)
        add_result(db, internal_id, "up", 100, now - timedelta(minutes=3), "u1")
        add_result(db, internal_id, "up", 300, now - timedelta(minutes=2), "u2")
        add_result(db, internal_id, "down", None, now - timedelta(minutes=1), "u3")
        add_result(db, internal_id, "up", 80, now, "u4")
        db.commit()

    response = client.get("/api/v1/monitors/uptime", headers=auth_headers)
    assert response.status_code == 200
    rows = {row["monitor_id"]: row for row in response.json()}
    assert set(rows) == {"site", "empty"}

    site = rows["site"]
    assert site["uptime_pct"] == 75.0  # 3 из 4
    assert site["checks_total"] == 4
    assert site["avg_response_ms"] == 160  # (100 + 300 + 80) / 3
    assert site["last_status"] == "up"
    assert site["last_response_ms"] == 80
    assert site["last_check_at"] is not None

    empty = rows["empty"]
    assert empty["uptime_pct"] is None
    assert empty["checks_total"] == 0
    assert empty["avg_response_ms"] is None
    assert empty["last_status"] is None


def test_monitors_uptime_viewer_access_and_org_isolation(client, monkeypatch):
    owner = register_and_login(client, "owner@example.com")
    viewer = register_and_login(client, "viewer@example.com")
    viewer_id = client.get("/api/v1/auth/me", headers=viewer).json()["id"]
    assert (
        client.patch(
            f"/api/v1/orgs/current/members/{viewer_id}", json={"role": "viewer"}, headers=owner
        ).status_code
        == 200
    )
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201

    # viewer видит uptime своей организации
    response = client.get("/api/v1/monitors/uptime", headers=viewer)
    assert response.status_code == 200
    assert [row["monitor_id"] for row in response.json()] == ["site"]

    # другая организация не видит чужие мониторы
    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")
    created = client.post("/api/v1/orgs", json={"name": "Other", "slug": "other"}, headers=owner)
    assert created.status_code == 201
    switched = client.post(f"/api/v1/orgs/{created.json()['id']}/switch", headers=owner)
    other_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}
    assert client.get("/api/v1/monitors/uptime", headers=other_headers).json() == []
