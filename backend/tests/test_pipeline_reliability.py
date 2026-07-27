from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base
from app.models import Monitor, Organization, SchedulerHeartbeat, User
from app.services.queue import (
    BROWSER_QUEUE,
    DEAD_LETTER_QUEUES,
    DLX_EXCHANGE,
    HTTP_QUEUE,
    declare_check_queue,
)


# --- DLQ topology -------------------------------------------------------------------------------


class FakeChannel:
    def __init__(self):
        self.exchanges = []
        self.queues = {}
        self.binds = []

    def exchange_declare(self, exchange, exchange_type, durable):
        self.exchanges.append((exchange, exchange_type, durable))

    def queue_declare(self, queue, durable, arguments=None):
        self.queues[queue] = {"durable": durable, "arguments": arguments}

    def queue_bind(self, queue, exchange, routing_key):
        self.binds.append((queue, exchange, routing_key))


def test_declare_check_queue_wires_dead_letter():
    channel = FakeChannel()
    declare_check_queue(channel, HTTP_QUEUE)

    # DLX объявлен как durable direct exchange
    assert (DLX_EXCHANGE, "direct", True) in channel.exchanges

    dlq = DEAD_LETTER_QUEUES[HTTP_QUEUE]
    assert dlq in channel.queues
    assert (dlq, DLX_EXCHANGE, dlq) in channel.binds

    # рабочая очередь ссылается на DLX
    args = channel.queues[HTTP_QUEUE]["arguments"]
    assert args["x-dead-letter-exchange"] == DLX_EXCHANGE
    assert args["x-dead-letter-routing-key"] == dlq


def test_both_queues_have_distinct_dlqs():
    assert DEAD_LETTER_QUEUES[HTTP_QUEUE] != DEAD_LETTER_QUEUES[BROWSER_QUEUE]
    for queue in (HTTP_QUEUE, BROWSER_QUEUE):
        channel = FakeChannel()
        declare_check_queue(channel, queue)
        assert channel.queues[queue]["arguments"]["x-dead-letter-routing-key"] == DEAD_LETTER_QUEUES[queue]


# --- heartbeat: запись шедулером -----------------------------------------------------------------


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.scheduler.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def test_write_heartbeat_inserts_then_updates(worker_session_factory):
    from app.workers.scheduler import write_heartbeat

    write_heartbeat()
    with worker_session_factory() as db:
        beats = db.scalars(select(SchedulerHeartbeat)).all()
        assert len(beats) == 1
        first = beats[0].beat_at

    write_heartbeat()
    with worker_session_factory() as db:
        beats = db.scalars(select(SchedulerHeartbeat)).all()
        # обновляется одна строка, не плодит новые
        assert len(beats) == 1
        assert beats[0].beat_at >= first


# --- /health/scheduler --------------------------------------------------------------------------


def set_heartbeat(db_session_factory, seconds_ago):
    with db_session_factory() as db:
        beat = db.get(SchedulerHeartbeat, 1)
        ts = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        if beat is None:
            db.add(SchedulerHeartbeat(id=1, beat_at=ts))
        else:
            beat.beat_at = ts
        db.commit()


def seed_overdue_monitor(db_session_factory, seconds_overdue):
    with db_session_factory() as db:
        user = User(email="hb@example.com", hashed_password="x")
        org = Organization(name="My team", slug="default")
        db.add_all([user, org])
        db.flush()
        db.add(
            Monitor(
                user_id=user.id,
                org_id=org.id,
                slug="overdue",
                name="Overdue",
                type="http",
                status="up",
                url="https://example.com",
                interval=60,
                config_json={},
                enabled=True,
                next_run_at=datetime.now(timezone.utc) - timedelta(seconds=seconds_overdue),
            )
        )
        db.commit()


def test_scheduler_health_503_without_heartbeat(client):
    response = client.get("/health/scheduler")
    assert response.status_code == 503
    assert response.json()["healthy"] is False
    assert response.json()["last_beat_at"] is None


def test_scheduler_health_200_when_fresh(client, db_session_factory):
    set_heartbeat(db_session_factory, seconds_ago=2)
    response = client.get("/health/scheduler")
    assert response.status_code == 200
    body = response.json()
    assert body["healthy"] is True
    assert body["lag_seconds"] < get_settings().scheduler_heartbeat_stale_seconds


def test_scheduler_health_503_when_stale(client, db_session_factory):
    set_heartbeat(db_session_factory, seconds_ago=get_settings().scheduler_heartbeat_stale_seconds + 30)
    response = client.get("/health/scheduler")
    assert response.status_code == 503
    assert response.json()["healthy"] is False


def test_scheduler_health_reports_overdue_monitors(client, db_session_factory):
    set_heartbeat(db_session_factory, seconds_ago=1)
    seed_overdue_monitor(db_session_factory, seconds_overdue=get_settings().scheduler_heartbeat_stale_seconds + 120)
    response = client.get("/health/scheduler")
    assert response.status_code == 200  # heartbeat свежий → сам шедулер жив
    assert response.json()["overdue_monitors"] == 1
