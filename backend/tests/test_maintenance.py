from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import AuditLog, MaintenanceWindow, Monitor, Organization, User

MONITOR_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def window_payload(minutes_from_now=-5, duration_minutes=60, monitor_id=None, note=None):
    starts = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    ends = starts + timedelta(minutes=duration_minutes)
    payload = {"monitor_id": monitor_id, "starts_at": starts.isoformat(), "ends_at": ends.isoformat()}
    if note is not None:
        payload["note"] = note
    return payload


# --- планировщик -------------------------------------------------------------------------------


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.scheduler.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


class FakePublisher:
    def __init__(self):
        self.tasks = []

    def publish(self, task):
        self.tasks.append(task)


def seed_org_with_monitors(session_factory, org_slug="default", slugs=("site",)):
    with session_factory() as db:
        user = User(email=f"{org_slug}@example.com", hashed_password="x")
        org = Organization(name="My team", slug=org_slug)
        db.add_all([user, org])
        db.flush()
        monitor_ids = []
        for slug in slugs:
            monitor = Monitor(
                user_id=user.id,
                org_id=org.id,
                slug=slug,
                name=slug,
                type="http",
                status="up",
                url="https://example.com",
                interval=60,
                config_json={},
                enabled=True,
                next_run_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            )
            db.add(monitor)
            db.flush()
            monitor_ids.append(monitor.id)
        db.commit()
        return org.id, monitor_ids


def add_window(session_factory, org_id, monitor_id=None, starts_delta=-30, ends_delta=30):
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        window = MaintenanceWindow(
            org_id=org_id,
            monitor_id=monitor_id,
            starts_at=now + timedelta(minutes=starts_delta),
            ends_at=now + timedelta(minutes=ends_delta),
        )
        db.add(window)
        db.commit()
        return window.ends_at


def test_scheduler_skips_monitor_in_personal_window(worker_session_factory):
    from app.workers.scheduler import publish_due_checks

    org_id, (monitor_id,) = seed_org_with_monitors(worker_session_factory)
    ends_at = add_window(worker_session_factory, org_id, monitor_id=monitor_id)

    publisher = FakePublisher()
    assert publish_due_checks(publisher) == 0
    assert publisher.tasks == []

    with worker_session_factory() as db:
        next_run_at = db.get(Monitor, monitor_id).next_run_at
    assert next_run_at.replace(tzinfo=timezone.utc) == ends_at


def test_scheduler_org_wide_window_covers_all_org_monitors(worker_session_factory):
    from app.workers.scheduler import publish_due_checks

    org_id, monitor_ids = seed_org_with_monitors(worker_session_factory, slugs=("one", "two"))
    other_org_id, (other_monitor_id,) = seed_org_with_monitors(
        worker_session_factory, org_slug="other", slugs=("free",)
    )
    ends_at = add_window(worker_session_factory, org_id, monitor_id=None)

    publisher = FakePublisher()
    # чужая организация без окна публикуется как обычно
    assert publish_due_checks(publisher) == 1
    assert [task.monitor_id for task in publisher.tasks] == [other_monitor_id]

    with worker_session_factory() as db:
        for monitor_id in monitor_ids:
            next_run_at = db.get(Monitor, monitor_id).next_run_at
            assert next_run_at.replace(tzinfo=timezone.utc) == ends_at


def test_scheduler_ignores_future_and_past_windows(worker_session_factory):
    from app.workers.scheduler import publish_due_checks

    org_id, (monitor_id,) = seed_org_with_monitors(worker_session_factory)
    add_window(worker_session_factory, org_id, monitor_id=monitor_id, starts_delta=60, ends_delta=120)  # будущее
    add_window(worker_session_factory, org_id, monitor_id=monitor_id, starts_delta=-120, ends_delta=-60)  # прошлое

    publisher = FakePublisher()
    assert publish_due_checks(publisher) == 1
    assert publisher.tasks[0].monitor_id == monitor_id


def test_scheduler_publishes_after_window_ends(worker_session_factory):
    from app.workers.scheduler import publish_due_checks

    org_id, (monitor_id,) = seed_org_with_monitors(worker_session_factory)
    add_window(worker_session_factory, org_id, monitor_id=monitor_id)

    # тик внутри окна: не опубликован, next_run_at == ends_at
    assert publish_due_checks(FakePublisher()) == 0

    # окно закончилось — сдвигаем его в прошлое, монитор снова due
    with worker_session_factory() as db:
        window = db.scalar(select(MaintenanceWindow))
        window.starts_at = datetime.now(timezone.utc) - timedelta(hours=2)
        window.ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
        monitor = db.get(Monitor, monitor_id)
        monitor.next_run_at = window.ends_at
        db.commit()

    publisher = FakePublisher()
    assert publish_due_checks(publisher) == 1
    assert publisher.tasks[0].monitor_id == monitor_id


# --- API ---------------------------------------------------------------------------------------


def test_create_requires_admin_member_forbidden(client):
    owner = register_and_login(client, "owner@example.com")
    member = register_and_login(client, "member@example.com")  # member по умолчанию

    assert client.post("/api/v1/maintenance", json=window_payload(), headers=member).status_code == 403

    response = client.post("/api/v1/maintenance", json=window_payload(note="db upgrade"), headers=owner)
    assert response.status_code == 201
    body = response.json()
    assert body["monitor_id"] is None
    assert body["monitor_name"] is None
    assert body["active"] is True
    assert body["note"] == "db upgrade"
    assert body["created_by_email"] == "owner@example.com"

    # viewer может читать список
    rows = client.get("/api/v1/maintenance", headers=member).json()
    assert len(rows) == 1


def test_create_validates_window_bounds(client, auth_headers):
    # ends_at <= starts_at
    starts = datetime.now(timezone.utc) + timedelta(hours=1)
    bad = {"monitor_id": None, "starts_at": starts.isoformat(), "ends_at": starts.isoformat()}
    assert client.post("/api/v1/maintenance", json=bad, headers=auth_headers).status_code == 422

    # окно целиком в прошлом
    assert (
        client.post(
            "/api/v1/maintenance",
            json=window_payload(minutes_from_now=-120, duration_minutes=60),
            headers=auth_headers,
        ).status_code
        == 422
    )


def test_create_for_foreign_or_missing_monitor_404(client, db_session_factory):
    owner = register_and_login(client, "owner@example.com")

    with db_session_factory() as db:
        foreign_user = User(email="foreign@example.com", hashed_password="x")
        foreign_org = Organization(name="Other", slug="other")
        db.add_all([foreign_user, foreign_org])
        db.flush()
        db.add(
            Monitor(
                user_id=foreign_user.id,
                org_id=foreign_org.id,
                slug="foreign-site",
                name="Foreign",
                type="http",
                status="up",
                url="https://example.com",
                interval=60,
                config_json={},
                enabled=True,
            )
        )
        db.commit()

    for slug in ("foreign-site", "ghost"):
        response = client.post("/api/v1/maintenance", json=window_payload(monitor_id=slug), headers=owner)
        assert response.status_code == 404


def test_delete_window_and_foreign_org_404(client, db_session_factory):
    owner = register_and_login(client, "owner@example.com")
    created = client.post("/api/v1/maintenance", json=window_payload(), headers=owner).json()

    # окно чужой организации недоступно
    with db_session_factory() as db:
        foreign_org = Organization(name="Other", slug="other")
        db.add(foreign_org)
        db.flush()
        foreign_window = MaintenanceWindow(
            org_id=foreign_org.id,
            starts_at=datetime.now(timezone.utc),
            ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(foreign_window)
        db.commit()
        foreign_id = foreign_window.id

    assert client.delete(f"/api/v1/maintenance/{foreign_id}", headers=owner).status_code == 404
    assert client.delete(f"/api/v1/maintenance/{created['id']}", headers=owner).status_code == 204
    assert client.get("/api/v1/maintenance", headers=owner).json() == []


def test_list_hides_old_windows_unless_include_past(client, auth_headers, db_session_factory):
    assert client.post("/api/v1/maintenance", json=window_payload(), headers=auth_headers).status_code == 201

    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "default"))
        db.add(
            MaintenanceWindow(
                org_id=org.id,
                starts_at=now - timedelta(days=10),
                ends_at=now - timedelta(days=9),
                note="ancient",
            )
        )
        db.commit()

    default_rows = client.get("/api/v1/maintenance", headers=auth_headers).json()
    assert len(default_rows) == 1
    assert default_rows[0]["active"] is True

    all_rows = client.get("/api/v1/maintenance?include_past=true", headers=auth_headers).json()
    assert len(all_rows) == 2
    # сортировка по starts_at DESC — старое окно последним
    assert all_rows[-1]["note"] == "ancient"
    assert all_rows[-1]["active"] is False


def test_monitors_list_reports_in_maintenance(client, auth_headers):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201

    monitors = client.get("/api/v1/monitors", headers=auth_headers).json()
    assert monitors[0]["in_maintenance"] is False

    assert (
        client.post("/api/v1/maintenance", json=window_payload(monitor_id="site"), headers=auth_headers).status_code
        == 201
    )
    monitors = client.get("/api/v1/monitors", headers=auth_headers).json()
    assert monitors[0]["in_maintenance"] is True


def test_status_page_maintenance_excluded_from_overall(client, auth_headers, db_session_factory):
    assert (
        client.patch("/api/v1/orgs/current", json={"status_page_enabled": True}, headers=auth_headers).status_code
        == 200
    )
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201
    with db_session_factory() as db:
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        monitor.status = "down"
        db.commit()

    # без окна down-монитор валит общий статус
    assert client.get("/api/v1/status/default").json()["overall"] == "down"

    assert (
        client.post("/api/v1/maintenance", json=window_payload(monitor_id="site"), headers=auth_headers).status_code
        == 201
    )
    # страница кэшируется на 15 секунд — окно только что создано, сбрасываем явно
    from app.api.v1.endpoints.status import _cache

    _cache.clear()
    body = client.get("/api/v1/status/default").json()
    assert body["overall"] == "operational"
    assert body["monitors"][0]["in_maintenance"] is True


def test_maintenance_create_writes_audit_event(client, auth_headers, db_session_factory):
    created = client.post("/api/v1/maintenance", json=window_payload(), headers=auth_headers)
    assert created.status_code == 201

    with db_session_factory() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.action == "maintenance.create")).all()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.entity == "maintenance"
    assert entry.entity_id == str(created.json()["id"])
    assert entry.payload["monitor"] == "all"
    assert "starts_at" in entry.payload and "ends_at" in entry.payload


def test_cancel_window_resumes_checks_immediately(client, auth_headers, db_session_factory):
    client.post(
        "/api/v1/monitors",
        json={"id": "site", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    created = client.post("/api/v1/maintenance", json=window_payload(duration_minutes=240), headers=auth_headers)
    assert created.status_code == 201

    # имитируем работу планировщика: проверка перенесена на конец 4-часового окна
    ends_at = datetime.fromisoformat(created.json()["ends_at"])
    with db_session_factory() as db:
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        monitor.next_run_at = ends_at
        db.commit()

    assert client.delete(f"/api/v1/maintenance/{created.json()['id']}", headers=auth_headers).status_code == 204

    # отмена окна вернула проверки сразу, а не через 4 часа
    now = datetime.now(timezone.utc)
    with db_session_factory() as db:
        next_run_at = db.scalar(select(Monitor.next_run_at).where(Monitor.slug == "site"))
    assert next_run_at.replace(tzinfo=timezone.utc) <= now
