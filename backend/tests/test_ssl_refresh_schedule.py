"""Периодичность снятия TLS-сертификата на стороне шедулера.

Раньше сертификат снимался на КАЖДОЙ http-проверке: отдельное соединение с
резолвом и полным хендшейком мимо основного запроса. Теперь просьба приходит
в задаче, а решает публикующая сторона — не чаще раза в сутки на монитор.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import Monitor, Organization, User
from app.services.queue import SSL_REFRESH_INTERVAL


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.scheduler.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


class FakePublisher:
    def __init__(self):
        self.tasks = []

    def publish(self, task):
        self.tasks.append(task)


def seed_monitor(session_factory, url="https://example.com", ssl_checked_at=None) -> int:
    with session_factory() as db:
        user = User(email="owner@example.com", hashed_password="x")
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
            url=url,
            interval=60,
            config_json={},
            enabled=True,
            next_run_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            ssl_checked_at=ssl_checked_at,
        )
        db.add(monitor)
        db.commit()
        return monitor.id


def publish_once(session_factory, monitor_id):
    """Один тик шедулера; монитор снова становится просроченным для следующего."""
    from app.workers.scheduler import publish_due_checks

    publisher = FakePublisher()
    assert publish_due_checks(publisher) == 1
    with session_factory() as db:
        db.get(Monitor, monitor_id).next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    return publisher.tasks[0]


def test_certificate_is_requested_once_a_day(worker_session_factory):
    monitor_id = seed_monitor(worker_session_factory)

    first = publish_once(worker_session_factory, monitor_id)
    assert first.collect_ssl is True
    with worker_session_factory() as db:
        assert db.get(Monitor, monitor_id).ssl_checked_at is not None

    # следующие проверки идут без отдельного соединения за сертификатом
    for _ in range(3):
        assert publish_once(worker_session_factory, monitor_id).collect_ssl is False

    # сутки прошли — снимаем снова
    with worker_session_factory() as db:
        monitor = db.get(Monitor, monitor_id)
        monitor.ssl_checked_at = datetime.now(timezone.utc) - SSL_REFRESH_INTERVAL - timedelta(minutes=1)
        db.commit()
    assert publish_once(worker_session_factory, monitor_id).collect_ssl is True


def test_plain_http_monitor_never_requests_certificate(worker_session_factory):
    monitor_id = seed_monitor(worker_session_factory, url="http://example.com")

    task = publish_once(worker_session_factory, monitor_id)
    assert task.collect_ssl is False
    with worker_session_factory() as db:
        assert db.get(Monitor, monitor_id).ssl_checked_at is None
