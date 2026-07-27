from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base
from app.models import Monitor, Organization, User
from app.services.plans import ensure_default_plans
from app.workers.scheduler import publish_due_checks

BROWSER_STEPS = [{"action": "goto", "url": "https://example.com"}]


@pytest.fixture()
def enterprise(monkeypatch):
    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")


@pytest.fixture()
def superuser_headers(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "superuser_emails", "root@example.com")
    payload = {"email": "root@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_monitor(client, headers, slug, **overrides):
    payload = {
        "id": slug,
        "name": slug,
        "type": "http",
        "url": "https://example.com",
        "interval": 600,
        **overrides,
    }
    return client.post("/api/v1/monitors", json=payload, headers=headers)


def set_default_org_plan(client, superuser_headers, plan_slug):
    org_id = client.get("/api/v1/admin/orgs", headers=superuser_headers).json()[0]["id"]
    response = client.put(
        f"/api/v1/admin/orgs/{org_id}/plan", headers=superuser_headers, json={"plan_slug": plan_slug}
    )
    assert response.status_code == 200
    return response.json()


def test_free_plan_monitor_limit(client, auth_headers, enterprise):
    for i in range(5):
        assert make_monitor(client, auth_headers, f"mon-{i}").status_code == 201
    response = make_monitor(client, auth_headers, "mon-5")
    assert response.status_code == 403
    assert "Plan 'Free'" in response.json()["detail"]


def test_free_plan_blocks_browser_monitors(client, auth_headers, enterprise):
    response = make_monitor(client, auth_headers, "b-1", type="browser", steps=BROWSER_STEPS)
    assert response.status_code == 403
    assert "browser" in response.json()["detail"]


def test_plan_min_interval_on_create(client, auth_headers, enterprise):
    response = make_monitor(client, auth_headers, "fast", interval=60)
    assert response.status_code == 400
    assert "every 300 seconds" in response.json()["detail"]


def test_plan_min_interval_on_update(client, auth_headers, enterprise):
    assert make_monitor(client, auth_headers, "slow").status_code == 201
    response = client.put("/api/v1/monitors/slow", headers=auth_headers, json={"interval": 60})
    assert response.status_code == 400


def test_disabled_monitor_not_counted(client, auth_headers, enterprise):
    for i in range(5):
        assert make_monitor(client, auth_headers, f"mon-{i}").status_code == 201
    # выключенный монитор не занимает слот и создаётся свободно
    assert make_monitor(client, auth_headers, "paused-one", enabled=False).status_code == 201
    # но включить его сверх лимита нельзя
    response = client.put("/api/v1/monitors/paused-one", headers=auth_headers, json={"enabled": True})
    assert response.status_code == 403


def test_config_upload_respects_plan(client, auth_headers, enterprise):
    monitors = "\n".join(
        f'  - id: cfg-{i}\n    type: http\n    url: https://example.com\n    interval: 600' for i in range(6)
    )
    content = f"version: 1\nmonitors:\n{monitors}\n"
    response = client.post(
        "/api/v1/config", headers=auth_headers, json={"content": content, "format": "yaml"}
    )
    assert response.status_code == 403
    assert "Plan 'Free'" in response.json()["detail"]


def test_team_mode_not_gated(client, auth_headers):
    # team-редакция живёт по env-лимитам, тарифы не применяются
    for i in range(6):
        assert make_monitor(client, auth_headers, f"team-{i}", interval=15).status_code == 201


def test_member_limit_on_explicit_add(client, enterprise, superuser_headers):
    # регистрация в default-организацию не блокируется лимитом плана
    client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "password123"})
    # свежая организация владельца: план free, max_members=1 — добавление второго запрещено
    org = client.post("/api/v1/orgs", headers=superuser_headers, json={"name": "Solo", "slug": "solo"}).json()
    switch = client.post(f"/api/v1/orgs/{org['id']}/switch", headers=superuser_headers, json={})
    switched_headers = {"Authorization": f"Bearer {switch.json()['access_token']}"}
    response = client.post(
        "/api/v1/orgs/current/members",
        headers=switched_headers,
        json={"email": "b@example.com", "role": "member"},
    )
    assert response.status_code == 403
    assert "Plan 'Free'" in response.json()["detail"]


def test_downgrade_pauses_excess_monitors(client, auth_headers, enterprise, superuser_headers):
    set_default_org_plan(client, superuser_headers, "business")
    assert make_monitor(client, auth_headers, "b-1", type="browser", steps=BROWSER_STEPS).status_code == 201
    for i in range(6):
        assert make_monitor(client, auth_headers, f"mon-{i}").status_code == 201

    result = set_default_org_plan(client, superuser_headers, "free")
    # 7 enabled: сверх лимита 5 — двое новейших; плюс browser в первой пятёрке (квота free = 0)
    assert sorted(result["paused_monitors"]) == ["b-1", "mon-4", "mon-5"]

    monitors = {m["id"]: m for m in client.get("/api/v1/monitors", headers=auth_headers).json()}
    assert monitors["b-1"]["status"] == "paused"
    assert monitors["mon-4"]["status"] == "paused"
    assert monitors["mon-5"]["status"] == "paused"
    assert monitors["mon-0"]["status"] != "paused"


def test_upgrade_pauses_nothing(client, auth_headers, enterprise, superuser_headers):
    for i in range(3):
        assert make_monitor(client, auth_headers, f"mon-{i}").status_code == 201
    result = set_default_org_plan(client, superuser_headers, "pro")
    assert result["paused_monitors"] == []


# --- клэмп интервала в шедулере -----------------------------------------------------------------


class FakePublisher:
    def __init__(self):
        self.tasks = []

    def publish(self, task):
        self.tasks.append(task)


@pytest.fixture()
def scheduler_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.scheduler.SessionLocal", factory)
    return factory


def seed_fast_monitor(session_factory, plan_slug="free"):
    with session_factory() as db:
        ensure_default_plans(db)
        user = User(email="sched@example.com", hashed_password="x")
        org = Organization(name="Org", slug="org", plan_slug=plan_slug)
        db.add_all([user, org])
        db.flush()
        monitor = Monitor(
            user_id=user.id,
            org_id=org.id,
            slug="fast",
            name="fast",
            type="http",
            status="up",
            url="https://example.com",
            interval=15,
            config_json={},
            enabled=True,
            next_run_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add(monitor)
        db.commit()
        return monitor.id


def next_run_delta(session_factory, monitor_id):
    with session_factory() as db:
        monitor = db.get(Monitor, monitor_id)
        next_run = monitor.next_run_at
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        return (next_run - datetime.now(timezone.utc)).total_seconds()


def test_scheduler_clamps_interval_to_plan(scheduler_session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")
    monitor_id = seed_fast_monitor(scheduler_session_factory)
    published = FakePublisher()
    assert publish_due_checks(published) == 1
    # free: минимум 300с — интервал монитора 15с клэмпится
    assert next_run_delta(scheduler_session_factory, monitor_id) > 250


def test_scheduler_no_clamp_in_team_mode(scheduler_session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "deployment_mode", "team")
    monitor_id = seed_fast_monitor(scheduler_session_factory)
    published = FakePublisher()
    assert publish_due_checks(published) == 1
    assert next_run_delta(scheduler_session_factory, monitor_id) < 60
