import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import Incident, Monitor, Organization, User
from app.schemas import CheckTask
from app.services.incidents import update_incident_for_status_change
from app.workers.base import persist_result

MONITOR_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def seed_monitor(db, slug="site", org_slug="default", email=None):
    user = User(email=email or f"{slug}@example.com", hashed_password="x")
    org = Organization(name="My team", slug=org_slug)
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
    return monitor


# --- сервис update_incident_for_status_change -------------------------------------------------


def test_up_to_down_opens_open_incident(db_session_factory):
    with db_session_factory() as db:
        monitor = seed_monitor(db)
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.commit()
        incident = db.scalar(select(Incident))
        assert incident.status == "open"
        assert incident.severity == "down"
        assert incident.org_id == monitor.org_id
        assert incident.monitor_id == monitor.id
        assert incident.trigger_error == "boom"
        assert incident.resolved_at is None
        assert incident.duration_seconds is None


def test_degraded_then_down_escalates_same_incident(db_session_factory):
    with db_session_factory() as db:
        monitor = seed_monitor(db)
        update_incident_for_status_change(db, monitor, "degraded", "slow")
        db.flush()
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.commit()
        incidents = db.scalars(select(Incident)).all()
        assert len(incidents) == 1
        assert incidents[0].severity == "down"  # поднялось до худшего
        assert incidents[0].status == "open"


def test_down_then_up_resolves_incident(db_session_factory):
    with db_session_factory() as db:
        monitor = seed_monitor(db)
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.flush()
        update_incident_for_status_change(db, monitor, "up", None)
        db.commit()
        incident = db.scalar(select(Incident))
        assert incident.status == "resolved"
        assert incident.resolved_at is not None
        assert incident.duration_seconds >= 0


def test_up_without_open_incident_is_noop(db_session_factory):
    with db_session_factory() as db:
        monitor = seed_monitor(db)
        update_incident_for_status_change(db, monitor, "up", None)
        db.commit()
        assert db.scalar(select(Incident)) is None


def test_degraded_then_up_yields_single_resolved_degraded(db_session_factory):
    with db_session_factory() as db:
        monitor = seed_monitor(db)
        update_incident_for_status_change(db, monitor, "degraded", "slow")
        db.flush()
        update_incident_for_status_change(db, monitor, "up", None)
        db.commit()
        incidents = db.scalars(select(Incident)).all()
        assert len(incidents) == 1
        assert incidents[0].status == "resolved"
        assert incidents[0].severity == "degraded"


# --- интеграция persist_result ----------------------------------------------------------------


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.base.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def seed_worker_monitor(session_factory, status="up"):
    with session_factory() as db:
        monitor = seed_monitor(db, email="worker@example.com")
        monitor.status = status
        db.commit()
        return monitor.id, monitor.org_id


def make_task(monitor_id, task_id):
    return CheckTask(
        task_id=task_id,
        monitor_id=monitor_id,
        type="http",
        url="https://example.com",
        config={},
        timeout_seconds=30,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    )


def test_persist_result_opens_then_closes_single_incident(worker_session_factory):
    monitor_id, org_id = seed_worker_monitor(worker_session_factory, status="up")

    asyncio.run(persist_result(make_task(monitor_id, "d1"), {"status": "down", "error": "boom", "details": {}}))
    asyncio.run(persist_result(make_task(monitor_id, "d2"), {"status": "down", "error": "boom", "details": {}}))
    asyncio.run(persist_result(make_task(monitor_id, "u1"), {"status": "up", "error": None, "details": {}}))

    with worker_session_factory() as db:
        incidents = db.scalars(select(Incident)).all()
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.status == "resolved"
        assert incident.severity == "down"
        assert incident.org_id == org_id
        assert incident.monitor_id == monitor_id
        assert incident.resolved_at is not None
        assert incident.duration_seconds >= 0


# --- API GET /incidents -----------------------------------------------------------------------


def test_incidents_api_isolation_filters_and_viewer(client, db_session_factory):
    owner = register_and_login(client, "owner@example.com")
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201

    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        my_org = db.scalar(select(Organization).where(Organization.slug == "default"))
        my_monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        db.add(
            Incident(
                org_id=my_org.id,
                monitor_id=my_monitor.id,
                status="open",
                severity="down",
                started_at=now,
                trigger_error="boom",
            )
        )
        db.add(
            Incident(
                org_id=my_org.id,
                monitor_id=my_monitor.id,
                status="resolved",
                severity="degraded",
                started_at=now - timedelta(hours=1),
                resolved_at=now - timedelta(minutes=30),
                duration_seconds=1800,
            )
        )
        # чужая организация — не должна быть видна
        other_monitor = seed_monitor(db, slug="foreign", org_slug="other", email="foreign@example.com")
        db.add(
            Incident(
                org_id=other_monitor.org_id,
                monitor_id=other_monitor.id,
                status="open",
                severity="down",
                started_at=now,
                trigger_error="x",
            )
        )
        db.commit()

    all_rows = client.get("/api/v1/incidents", headers=owner).json()
    assert len(all_rows) == 2
    assert all(row["monitor_slug"] == "site" for row in all_rows)
    assert all(row["monitor_name"] == "site" for row in all_rows)  # name = slug при создании без name
    # порядок по started_at DESC — open (сейчас) первым
    assert all_rows[0]["status"] == "open"

    open_rows = client.get("/api/v1/incidents?status=open", headers=owner).json()
    assert len(open_rows) == 1
    assert open_rows[0]["status"] == "open"

    resolved_rows = client.get("/api/v1/incidents?status=resolved", headers=owner).json()
    assert len(resolved_rows) == 1
    assert resolved_rows[0]["duration_seconds"] == 1800

    by_monitor = client.get("/api/v1/incidents?monitor_id=site", headers=owner).json()
    assert len(by_monitor) == 2
    # чужой монитор недоступен из этой организации
    assert client.get("/api/v1/incidents?monitor_id=foreign", headers=owner).json() == []

    # viewer имеет доступ на чтение
    viewer = register_and_login(client, "viewer@example.com")
    viewer_id = client.get("/api/v1/auth/me", headers=viewer).json()["id"]
    assert (
        client.patch(
            f"/api/v1/orgs/current/members/{viewer_id}", json={"role": "viewer"}, headers=owner
        ).status_code
        == 200
    )
    assert client.get("/api/v1/incidents", headers=viewer).status_code == 200


def test_monitor_incidents_endpoint_and_route_order(client, db_session_factory):
    owner = register_and_login(client, "owner@example.com")
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201

    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "default"))
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        db.add(
            Incident(
                org_id=org.id,
                monitor_id=monitor.id,
                status="open",
                severity="down",
                started_at=now,
                trigger_error="boom",
            )
        )
        db.commit()

    rows = client.get("/api/v1/monitors/site/incidents", headers=owner).json()
    assert len(rows) == 1
    assert rows[0]["monitor_slug"] == "site"
    # /monitors/{slug}/incidents не перехватывается /monitors/{monitor_id}
    assert client.get("/api/v1/monitors/ghost/incidents", headers=owner).status_code == 404


# --- инцидент закрывается, когда монитор останавливают мимо пайплайна ---------------------------


def test_resolve_open_incident_closes_and_is_idempotent(db_session_factory):
    from app.services.incidents import resolve_open_incident

    with db_session_factory() as db:
        monitor = seed_monitor(db)
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.flush()

        assert resolve_open_incident(db, monitor.id) is not None
        db.commit()
        incident = db.scalar(select(Incident))
        assert incident.status == "resolved"
        assert incident.resolved_at is not None
        assert incident.duration_seconds >= 0

        # повторный вызов уже нечего закрывать — не создаёт и не портит запись
        assert resolve_open_incident(db, monitor.id) is None


def test_archiving_monitor_closes_its_open_incident(client, db_session_factory):
    """Архивация убирает монитор из продукта — инцидент не должен остаться открытым."""
    headers = register_and_login(client, "archive-incident@example.com")
    client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=headers)

    with db_session_factory() as db:
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.commit()

    assert client.delete("/api/v1/monitors/site", headers=headers).status_code == 204

    with db_session_factory() as db:
        incident = db.scalar(select(Incident))
        assert incident.status == "resolved"
        assert incident.resolved_at is not None


def test_pausing_monitor_closes_its_open_incident(client, db_session_factory):
    """Пауза через UI останавливает проверки: закрыть инцидент больше некому."""
    headers = register_and_login(client, "pause-incident@example.com")
    client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=headers)

    with db_session_factory() as db:
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.commit()

    response = client.put("/api/v1/monitors/site", json={"enabled": False}, headers=headers)
    assert response.status_code == 200

    with db_session_factory() as db:
        assert db.scalar(select(Incident)).status == "resolved"


def test_monitor_dropped_from_config_closes_its_open_incident(client, db_session_factory):
    """Ресинк конфига выключает отсутствующие мониторы — с тем же следствием."""
    headers = register_and_login(client, "config-incident@example.com")
    client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=headers)

    with db_session_factory() as db:
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.commit()

    response = client.post(
        "/api/v1/config",
        json={"content": "version: 1\nmonitors: []\n", "format": "yaml"},
        headers=headers,
    )
    assert response.status_code == 200

    with db_session_factory() as db:
        assert db.scalar(select(Incident)).status == "resolved"


def test_plan_downgrade_closes_incidents_of_paused_monitors(db_session_factory, monkeypatch):
    """Даунгрейд тарифа гасит мониторы сверх лимита — их инциденты тоже закрываются."""
    from app.models import Plan
    from app.services.plans import apply_plan_downgrade

    monkeypatch.setattr("app.services.plans.plan_gating_active", lambda: True)

    with db_session_factory() as db:
        db.add(Plan(
            slug="tiny", name="Tiny", price_monthly_kopeks=0, annual_discount_pct=0,
            max_monitors=1, min_interval_seconds=60, max_browser_monitors=0,
            browser_min_interval_seconds=300, max_members=1, retention_days=30, sort_order=0,
        ))
        db.flush()
        first = seed_monitor(db, slug="keep", org_slug="downgrade", email="dg@example.com")
        second = Monitor(
            user_id=first.user_id, org_id=first.org_id, slug="drop", name="Drop", type="http",
            status="down", url="https://example.com", interval=60, config_json={}, enabled=True,
        )
        db.add(second)
        db.flush()
        update_incident_for_status_change(db, second, "down", "boom")
        org = db.get(Organization, first.org_id)
        org.plan_slug = "tiny"
        db.flush()

        paused = apply_plan_downgrade(db, org)
        db.commit()

        assert "drop" in paused
        assert db.scalar(select(Incident).where(Incident.monitor_id == second.id)).status == "resolved"
