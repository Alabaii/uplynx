import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.security import encrypt_secret
from app.models import Incident, Monitor, Organization, TelegramIntegration, User
from app.schemas import CheckTask
from app.workers.base import persist_result, renotify_due


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.base.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def seed_down_monitor(session_factory, config_json=None, incident_started_minutes_ago=10, with_incident=True):
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        user = User(email="worker@example.com", hashed_password="x")
        org = Organization(name="My team", slug="default")
        db.add_all([user, org])
        db.flush()
        monitor = Monitor(
            user_id=user.id,
            org_id=org.id,
            slug="site",
            name="Site",
            type="http",
            status="down",
            url="https://example.com",
            interval=60,
            config_json=config_json or {},
            enabled=True,
        )
        db.add(monitor)
        db.flush()
        if with_incident:
            db.add(
                Incident(
                    org_id=org.id,
                    monitor_id=monitor.id,
                    status="open",
                    severity="down",
                    started_at=now - timedelta(minutes=incident_started_minutes_ago),
                    trigger_error="boom",
                )
            )
        db.add(
            TelegramIntegration(
                user_id=user.id,
                org_id=org.id,
                bot_token_secret=encrypt_secret("123456:secret-token"),
                chat_id="42",
                alert_scopes=["down", "degraded", "recovered"],
            )
        )
        db.commit()
        return monitor.id


def make_task(monitor_id, task_id="t1"):
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


def capture_telegram(monkeypatch):
    calls = []

    async def fake_send(bot_token, chat_id, text):
        calls.append(text)
        return True

    monkeypatch.setattr("app.workers.base.send_telegram_message", fake_send)
    return calls


# --- renotify_due -------------------------------------------------------------------------------


def test_renotify_due_off_without_interval():
    incident = Incident(started_at=datetime.now(timezone.utc) - timedelta(hours=5))
    assert renotify_due(incident, {}, datetime.now(timezone.utc)) is False
    assert renotify_due(incident, None, datetime.now(timezone.utc)) is False


def test_renotify_due_counts_from_started_at_when_never_renotified():
    now = datetime.now(timezone.utc)
    incident = Incident(started_at=now - timedelta(minutes=6))
    assert renotify_due(incident, {"renotify_interval_minutes": 5}, now) is True
    assert renotify_due(incident, {"renotify_interval_minutes": 10}, now) is False


def test_renotify_due_counts_from_last_notified_at():
    now = datetime.now(timezone.utc)
    incident = Incident(
        started_at=now - timedelta(hours=2),
        last_notified_at=now - timedelta(minutes=3),
    )
    assert renotify_due(incident, {"renotify_interval_minutes": 5}, now) is False
    incident.last_notified_at = now - timedelta(minutes=7)
    assert renotify_due(incident, {"renotify_interval_minutes": 5}, now) is True


def test_renotify_due_handles_naive_datetime():
    now = datetime.now(timezone.utc)
    incident = Incident(started_at=(now - timedelta(minutes=6)).replace(tzinfo=None))
    assert renotify_due(incident, {"renotify_interval_minutes": 5}, now) is True


# --- persist_result -----------------------------------------------------------------------------


def test_renotify_sent_when_interval_elapsed(worker_session_factory, monkeypatch):
    monitor_id = seed_down_monitor(
        worker_session_factory,
        config_json={"renotify_interval_minutes": 5},
        incident_started_minutes_ago=10,
    )
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "r1"), {"status": "down", "error": "boom", "details": {}}))

    assert len(calls) == 1
    assert "still down" in calls[0]
    assert "10 min" in calls[0]

    with worker_session_factory() as db:
        incident = db.scalar(select(Incident))
        assert incident.last_notified_at is not None

    # следующая проверка сразу после алерта — интервал ещё не прошёл, повторов нет
    asyncio.run(persist_result(make_task(monitor_id, "r2"), {"status": "down", "error": "boom", "details": {}}))
    assert len(calls) == 1


def test_renotify_not_sent_before_interval(worker_session_factory, monkeypatch):
    monitor_id = seed_down_monitor(
        worker_session_factory,
        config_json={"renotify_interval_minutes": 15},
        incident_started_minutes_ago=10,
    )
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "r1"), {"status": "down", "error": "boom", "details": {}}))
    assert calls == []


def test_renotify_disabled_by_default(worker_session_factory, monkeypatch):
    monitor_id = seed_down_monitor(worker_session_factory, incident_started_minutes_ago=600)
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "r1"), {"status": "down", "error": "boom", "details": {}}))
    assert calls == []


def test_renotify_skipped_without_open_incident(worker_session_factory, monkeypatch):
    monitor_id = seed_down_monitor(
        worker_session_factory,
        config_json={"renotify_interval_minutes": 5},
        with_incident=False,
    )
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "r1"), {"status": "down", "error": "boom", "details": {}}))
    assert calls == []


def test_recovery_still_sends_recovered_not_renotify(worker_session_factory, monkeypatch):
    monitor_id = seed_down_monitor(
        worker_session_factory,
        config_json={"renotify_interval_minutes": 5},
        incident_started_minutes_ago=10,
    )
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "r1"), {"status": "up", "error": None, "details": {}}))

    assert len(calls) == 1
    assert "recovered" in calls[0]
    with worker_session_factory() as db:
        incident = db.scalar(select(Incident))
        assert incident.status == "resolved"


# --- конфиг -------------------------------------------------------------------------------------


def test_renotify_roundtrip_through_config(client, auth_headers):
    payload = {
        "id": "site",
        "type": "http",
        "url": "https://example.com",
        "interval": 60,
        "renotify_interval_minutes": 30,
    }
    created = client.post("/api/v1/monitors", json=payload, headers=auth_headers)
    assert created.status_code == 201
    assert created.json()["config"]["renotify_interval_minutes"] == 30

    config = client.get("/api/v1/config", headers=auth_headers).json()
    assert "renotify_interval_minutes: 30" in config["content"]

    # выгруженный конфиг валиден и принимается обратно
    upload = client.post(
        "/api/v1/config",
        json={"content": config["content"], "format": "yaml"},
        headers=auth_headers,
    )
    assert upload.status_code == 200
    monitor = client.get("/api/v1/monitors/site", headers=auth_headers).json()
    assert monitor["config"]["renotify_interval_minutes"] == 30


def test_renotify_validation_bounds(client, auth_headers):
    payload = {
        "id": "site",
        "type": "http",
        "url": "https://example.com",
        "interval": 60,
        "renotify_interval_minutes": 0,
    }
    assert client.post("/api/v1/monitors", json=payload, headers=auth_headers).status_code == 422
    payload["renotify_interval_minutes"] = 2000
    assert client.post("/api/v1/monitors", json=payload, headers=auth_headers).status_code == 422
