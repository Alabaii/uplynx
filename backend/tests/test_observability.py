import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.observability import init_sentry, start_metrics_server
from app.models import Monitor, Organization, User
from app.schemas import CheckTask
from app.services.queue import DEAD_LETTER_QUEUES, HTTP_QUEUE
from app.workers.base import process_message


def sample(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


# --- init: без конфигурации всё выключено --------------------------------------------------------


def test_sentry_noop_without_dsn():
    assert init_sentry("test") is False


def test_metrics_server_disabled_without_port():
    assert start_metrics_server() is False


# --- /metrics на API ------------------------------------------------------------------------------


def test_api_metrics_endpoint(client):
    assert client.get("/health").status_code == 200

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "uplynx_http_requests_total" in response.text
    # метрика размечена шаблоном маршрута, /health посчитан
    assert 'path="/health"' in response.text


def test_api_metrics_do_not_count_metrics_endpoint(client):
    client.get("/metrics")
    response = client.get("/metrics")
    assert 'path="/metrics"' not in response.text


# --- метрики воркера ------------------------------------------------------------------------------


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.base.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def seed_monitor(session_factory):
    with session_factory() as db:
        user = User(email="obs@example.com", hashed_password="x")
        org = Organization(name="My team", slug="default")
        db.add_all([user, org])
        db.flush()
        monitor = Monitor(
            user_id=user.id,
            org_id=org.id,
            slug="site",
            name="Site",
            type="http",
            status="up",
            url="https://example.com",
            interval=60,
            config_json={},
            enabled=True,
        )
        db.add(monitor)
        db.commit()
        return monitor.id


def make_body(monitor_id, task_id):
    return CheckTask(
        task_id=task_id,
        monitor_id=monitor_id,
        type="http",
        url="https://example.com",
        config={},
        timeout_seconds=30,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    ).model_dump_json().encode()


async def up_runner(task):
    return {"status": "up", "response_time_ms": 5, "error": None, "details": {}}


def test_process_message_success_counts(worker_session_factory):
    monitor_id = seed_monitor(worker_session_factory)
    before = sample("uplynx_checks_processed_total", {"queue": HTTP_QUEUE, "result": "up"}) or 0

    assert process_message(HTTP_QUEUE, up_runner, make_body(monitor_id, "m1")) is True

    assert sample("uplynx_checks_processed_total", {"queue": HTTP_QUEUE, "result": "up"}) == before + 1


def test_process_message_failure_counts_dead_letter(worker_session_factory):
    before_err = sample("uplynx_checks_processed_total", {"queue": HTTP_QUEUE, "result": "error"}) or 0
    before_dlq = sample("uplynx_checks_dead_lettered_total", {"queue": HTTP_QUEUE}) or 0

    assert process_message(HTTP_QUEUE, up_runner, b"not-json{{{") is False

    assert sample("uplynx_checks_processed_total", {"queue": HTTP_QUEUE, "result": "error"}) == before_err + 1
    assert sample("uplynx_checks_dead_lettered_total", {"queue": HTTP_QUEUE}) == before_dlq + 1


# --- метрики шедулера -----------------------------------------------------------------------------


class FakeMethod:
    def __init__(self, count):
        self.method = type("M", (), {"message_count": count})()


class FakePublisher:
    def __init__(self, dlq_counts=None):
        self.tasks = []
        self.dlq_counts = dlq_counts or {}

    def publish(self, task):
        self.tasks.append(task)

    def declare_queue(self, queue):
        return FakeMethod(self.dlq_counts.get(queue, 0))


def test_publish_due_checks_increments_counter(worker_session_factory, monkeypatch):
    from app.workers.scheduler import publish_due_checks

    monkeypatch.setattr("app.workers.scheduler.SessionLocal", worker_session_factory)
    monitor_id = seed_monitor(worker_session_factory)
    with worker_session_factory() as db:
        db.get(Monitor, monitor_id).next_run_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()

    before = sample("uplynx_scheduler_published_total") or 0
    assert publish_due_checks(FakePublisher()) == 1
    assert sample("uplynx_scheduler_published_total") == before + 1


def test_update_pipeline_gauges(worker_session_factory, monkeypatch):
    from app.workers.scheduler import update_pipeline_gauges

    monkeypatch.setattr("app.workers.scheduler.SessionLocal", worker_session_factory)
    monitor_id = seed_monitor(worker_session_factory)
    with worker_session_factory() as db:
        # монитор просрочен сильнее порога — попадает в overdue
        db.get(Monitor, monitor_id).next_run_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()

    dlq_counts = {name: 7 for name in DEAD_LETTER_QUEUES.values()}
    update_pipeline_gauges(FakePublisher(dlq_counts=dlq_counts))

    assert sample("uplynx_scheduler_overdue_monitors") == 1
    for dead_queue in DEAD_LETTER_QUEUES.values():
        assert sample("uplynx_dlq_depth", {"queue": dead_queue}) == 7


def test_worker_runs_are_timed(worker_session_factory):
    monitor_id = seed_monitor(worker_session_factory)
    process_message(HTTP_QUEUE, up_runner, make_body(monitor_id, "m2"))
    count = sample("uplynx_check_processing_seconds_count", {"queue": HTTP_QUEUE})
    assert count is not None and count >= 1
