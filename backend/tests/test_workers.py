import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.security import encrypt_secret
from app.models import CheckResult, Monitor, TelegramIntegration, User
from app.schemas import CheckTask
from app.services.checks import run_browser_check
from app.workers.base import persist_result


class FakeRunner:
    async def run(self, task):
        return {"status": "up", "response_time_ms": 5, "error": None, "details": {"task": task.task_id}}


@pytest.mark.asyncio
async def test_browser_worker_adapter_mocked():
    task = CheckTask(
        task_id="b1",
        monitor_id=1,
        type="browser",
        config={"steps": [{"action": "assert_text", "text": "ok"}]},
        timeout_seconds=30,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    )
    result = await run_browser_check(task, runner=FakeRunner())
    assert result["status"] == "up"


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.base.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def seed_monitor(session_factory, status="up", with_integration=True):
    with session_factory() as db:
        user = User(email="worker@example.com", hashed_password="x")
        db.add(user)
        db.flush()
        monitor = Monitor(
            user_id=user.id,
            slug="site",
            name="Site",
            type="http",
            status=status,
            url="https://example.com",
            interval=60,
            config_json={},
            enabled=True,
            next_run_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        db.add(monitor)
        if with_integration:
            db.add(
                TelegramIntegration(
                    user_id=user.id,
                    bot_token_secret=encrypt_secret("123456:secret-token"),
                    chat_id="42",
                    alert_scopes=["down", "recovered"],
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


def test_persist_result_does_not_touch_next_run_at(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, with_integration=False)
    with worker_session_factory() as db:
        before = db.get(Monitor, monitor_id).next_run_at

    asyncio.run(persist_result(make_task(monitor_id), {"status": "down", "error": "boom", "details": {}}))

    with worker_session_factory() as db:
        monitor = db.get(Monitor, monitor_id)
        assert monitor.next_run_at == before
        assert monitor.status == "down"
        assert db.scalar(select(CheckResult).where(CheckResult.task_id == "t1")) is not None


def test_alert_sent_on_status_change(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, status="up")
    calls = []

    async def fake_send(bot_token, chat_id, text):
        calls.append((bot_token, chat_id, text))
        return True

    monkeypatch.setattr("app.workers.base.send_telegram_message", fake_send)

    asyncio.run(persist_result(make_task(monitor_id, "a1"), {"status": "down", "error": "boom", "details": {}}))
    assert len(calls) == 1
    assert calls[0][0] == "123456:secret-token"
    assert calls[0][1] == "42"
    assert "down" in calls[0][2]

    # тот же статус повторно — алерт не дублируется
    asyncio.run(persist_result(make_task(monitor_id, "a2"), {"status": "down", "error": "boom", "details": {}}))
    assert len(calls) == 1

    # восстановление — recovered
    asyncio.run(persist_result(make_task(monitor_id, "a3"), {"status": "up", "error": None, "details": {}}))
    assert len(calls) == 2
    assert "recovered" in calls[1][2]


def test_alert_failure_does_not_break_persist(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, status="up")

    async def failing_send(bot_token, chat_id, text):
        raise RuntimeError("telegram is down")

    monkeypatch.setattr("app.workers.base.send_telegram_message", failing_send)

    asyncio.run(persist_result(make_task(monitor_id, "f1"), {"status": "down", "error": "boom", "details": {}}))

    with worker_session_factory() as db:
        assert db.scalar(select(CheckResult).where(CheckResult.task_id == "f1")) is not None
        assert db.get(Monitor, monitor_id).status == "down"


def test_scheduler_publishes_due_and_advances_next_run_at(worker_session_factory, monkeypatch):
    from app.workers.scheduler import publish_due_checks

    monkeypatch.setattr("app.workers.scheduler.SessionLocal", worker_session_factory)
    monitor_id = seed_monitor(worker_session_factory, with_integration=False)

    published = []

    class FakePublisher:
        def publish(self, task):
            published.append(task)

    count = publish_due_checks(FakePublisher())
    assert count == 1
    assert published[0].monitor_id == monitor_id

    with worker_session_factory() as db:
        next_run_at = db.get(Monitor, monitor_id).next_run_at
    assert next_run_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    # монитор больше не due — повторная итерация ничего не публикует
    assert publish_due_checks(FakePublisher()) == 0
