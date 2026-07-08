import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.core.security import encrypt_secret
from app.models import CheckResult, Monitor, Organization, PushSubscription, TelegramIntegration, User
from app.schemas import CheckTask
from app.services.checks import run_browser_check
from app.services.webpush import PushSubscriptionGone
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


def seed_monitor(session_factory, status="up", with_integration=True, config_json=None):
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
            status=status,
            url="https://example.com",
            interval=60,
            config_json=config_json or {},
            enabled=True,
            next_run_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        db.add(monitor)
        if with_integration:
            db.add(
                TelegramIntegration(
                    user_id=user.id,
                    org_id=org.id,
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


def test_confirmations_suppress_single_flap(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, status="up", config_json={"confirmations": 2})
    calls = []

    async def fake_send(bot_token, chat_id, text):
        calls.append(text)
        return True

    monkeypatch.setattr("app.workers.base.send_telegram_message", fake_send)

    # первый down — сырой результат сохранён, но эффективный статус не меняется, алерта нет
    asyncio.run(persist_result(make_task(monitor_id, "c1"), {"status": "down", "error": "boom", "details": {}}))
    with worker_session_factory() as db:
        assert db.get(Monitor, monitor_id).status == "up"
        assert db.scalar(select(CheckResult).where(CheckResult.task_id == "c1")).status == "down"
    assert calls == []

    # второй down подряд — статус переключается, алерт ровно один
    asyncio.run(persist_result(make_task(monitor_id, "c2"), {"status": "down", "error": "boom", "details": {}}))
    with worker_session_factory() as db:
        assert db.get(Monitor, monitor_id).status == "down"
    assert len(calls) == 1
    assert "down" in calls[0]


def test_confirmations_interrupted_series_keeps_status(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, status="up", config_json={"confirmations": 2})
    calls = []

    async def fake_send(bot_token, chat_id, text):
        calls.append(text)
        return True

    monkeypatch.setattr("app.workers.base.send_telegram_message", fake_send)

    # down-up-down: серия прервана, статус остаётся up
    for task_id, raw in (("i1", "down"), ("i2", "up"), ("i3", "down")):
        asyncio.run(persist_result(make_task(monitor_id, task_id), {"status": raw, "error": None, "details": {}}))

    with worker_session_factory() as db:
        assert db.get(Monitor, monitor_id).status == "up"
        assert db.scalar(select(func.count()).select_from(CheckResult)) == 3
    assert calls == []


def test_pending_monitor_gets_status_immediately(worker_session_factory):
    monitor_id = seed_monitor(
        worker_session_factory, status="pending", with_integration=False, config_json={"confirmations": 5}
    )

    asyncio.run(persist_result(make_task(monitor_id, "n1"), {"status": "up", "error": None, "details": {}}))

    with worker_session_factory() as db:
        assert db.get(Monitor, monitor_id).status == "up"


def test_alert_uses_org_integration_not_creators(worker_session_factory, monkeypatch):
    # монитор создал user A, интеграцию настроил user B (admin) той же организации
    with worker_session_factory() as db:
        creator = User(email="creator@example.com", hashed_password="x")
        admin = User(email="admin@example.com", hashed_password="x")
        org = Organization(name="My team", slug="default")
        db.add_all([creator, admin, org])
        db.flush()
        monitor = Monitor(
            user_id=creator.id,
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
        db.add(
            TelegramIntegration(
                user_id=admin.id,
                org_id=org.id,
                bot_token_secret=encrypt_secret("123456:org-wide-token"),
                chat_id="99",
                alert_scopes=["down"],
            )
        )
        db.commit()
        monitor_id = monitor.id

    calls = []

    async def fake_send(bot_token, chat_id, text):
        calls.append((bot_token, chat_id, text))
        return True

    monkeypatch.setattr("app.workers.base.send_telegram_message", fake_send)

    asyncio.run(persist_result(make_task(monitor_id, "org1"), {"status": "down", "error": "boom", "details": {}}))
    assert len(calls) == 1
    assert calls[0][0] == "123456:org-wide-token"
    assert calls[0][1] == "99"


def test_alert_failure_does_not_break_persist(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, status="up")

    async def failing_send(bot_token, chat_id, text):
        raise RuntimeError("telegram is down")

    monkeypatch.setattr("app.workers.base.send_telegram_message", failing_send)

    asyncio.run(persist_result(make_task(monitor_id, "f1"), {"status": "down", "error": "boom", "details": {}}))

    with worker_session_factory() as db:
        assert db.scalar(select(CheckResult).where(CheckResult.task_id == "f1")) is not None
        assert db.get(Monitor, monitor_id).status == "down"


def enable_push(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")


def add_push_subscription(session_factory, endpoint):
    with session_factory() as db:
        org = db.scalar(select(Organization))
        user = db.scalar(select(User))
        db.add(PushSubscription(org_id=org.id, user_id=user.id, endpoint=endpoint, p256dh="p", auth="a"))
        db.commit()


def test_push_alerts_sent_to_all_org_subscriptions(worker_session_factory, monkeypatch):
    enable_push(monkeypatch)
    monitor_id = seed_monitor(worker_session_factory, status="up", with_integration=False)
    add_push_subscription(worker_session_factory, "https://push.example/one")
    add_push_subscription(worker_session_factory, "https://push.example/two")

    pushed = []

    def fake_push(subscription, title, body, url="/"):
        pushed.append((subscription.endpoint, title, body, url))
        return True

    monkeypatch.setattr("app.workers.base.send_web_push", fake_push)

    asyncio.run(persist_result(make_task(monitor_id, "p1"), {"status": "down", "error": "boom", "details": {}}))

    assert sorted(item[0] for item in pushed) == ["https://push.example/one", "https://push.example/two"]
    assert pushed[0][1] == "site is DOWN"
    assert "down" in pushed[0][2]
    assert pushed[0][3] == "/monitors/site"

    # тот же статус повторно — push не дублируется
    asyncio.run(persist_result(make_task(monitor_id, "p2"), {"status": "down", "error": "boom", "details": {}}))
    assert len(pushed) == 2


def test_push_dead_subscription_removed(worker_session_factory, monkeypatch):
    enable_push(monkeypatch)
    monitor_id = seed_monitor(worker_session_factory, status="up", with_integration=False)
    add_push_subscription(worker_session_factory, "https://push.example/alive")
    add_push_subscription(worker_session_factory, "https://push.example/dead")

    def fake_push(subscription, title, body, url="/"):
        if subscription.endpoint.endswith("/dead"):
            raise PushSubscriptionGone
        return True

    monkeypatch.setattr("app.workers.base.send_web_push", fake_push)

    asyncio.run(persist_result(make_task(monitor_id, "p1"), {"status": "down", "error": "boom", "details": {}}))

    with worker_session_factory() as db:
        endpoints = [row.endpoint for row in db.scalars(select(PushSubscription)).all()]
        assert endpoints == ["https://push.example/alive"]
        # результат проверки сохранён несмотря на мёртвую подписку
        assert db.scalar(select(CheckResult).where(CheckResult.task_id == "p1")) is not None


def test_push_skipped_without_vapid_keys(worker_session_factory, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", None)
    monkeypatch.setattr(settings, "vapid_private_key", None)
    monitor_id = seed_monitor(worker_session_factory, status="up", with_integration=False)
    add_push_subscription(worker_session_factory, "https://push.example/one")

    pushed = []
    monkeypatch.setattr("app.workers.base.send_web_push", lambda *args, **kwargs: pushed.append(args))

    asyncio.run(persist_result(make_task(monitor_id, "p1"), {"status": "down", "error": "boom", "details": {}}))
    assert pushed == []


def set_alert_emails(session_factory, emails):
    with session_factory() as db:
        org = db.scalar(select(Organization))
        org.alert_emails = emails
        db.commit()


def test_email_alerts_sent_to_all_addresses(worker_session_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.test")
    monitor_id = seed_monitor(worker_session_factory, status="up", with_integration=False)
    set_alert_emails(worker_session_factory, ["ops@example.com", "oncall@example.com"])

    sent = []

    def fake_send(to, subject, body):
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr("app.workers.base.send_email", fake_send)

    asyncio.run(persist_result(make_task(monitor_id, "e1"), {"status": "down", "error": "boom", "details": {}}))

    assert sorted(item[0] for item in sent) == ["oncall@example.com", "ops@example.com"]
    assert sent[0][1] == "[DOWN] Site"
    assert "down" in sent[0][2]

    # тот же статус повторно — письма не дублируются
    asyncio.run(persist_result(make_task(monitor_id, "e2"), {"status": "down", "error": "boom", "details": {}}))
    assert len(sent) == 2


def test_email_alerts_skipped_when_disabled_or_no_recipients(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, status="up", with_integration=False)
    sent = []
    monkeypatch.setattr("app.workers.base.send_email", lambda *args: sent.append(args) or True)

    # SMTP не настроен — писем нет, даже если адреса заданы
    monkeypatch.setattr(get_settings(), "smtp_host", None)
    set_alert_emails(worker_session_factory, ["ops@example.com"])
    asyncio.run(persist_result(make_task(monitor_id, "d1"), {"status": "down", "error": "boom", "details": {}}))
    assert sent == []

    # SMTP настроен, но адресов нет — писем тоже нет
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.test")
    set_alert_emails(worker_session_factory, [])
    asyncio.run(persist_result(make_task(monitor_id, "d2"), {"status": "up", "error": None, "details": {}}))
    assert sent == []


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


def test_scheduler_fair_share_between_orgs(worker_session_factory, monkeypatch):
    from app.workers.scheduler import publish_due_checks

    monkeypatch.setattr("app.workers.scheduler.SessionLocal", worker_session_factory)
    monkeypatch.setattr(get_settings(), "scheduler_org_batch_limit", 2)

    due_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    with worker_session_factory() as db:
        user = User(email="fair@example.com", hashed_password="x")
        big = Organization(name="Big", slug="big")
        small = Organization(name="Small", slug="small")
        db.add_all([user, big, small])
        db.flush()
        for org, count in ((big, 5), (small, 1)):
            for idx in range(count):
                db.add(
                    Monitor(
                        user_id=user.id,
                        org_id=org.id,
                        slug=f"{org.slug}-{idx}",
                        name=f"{org.slug}-{idx}",
                        type="http",
                        status="up",
                        url="https://example.com",
                        interval=60,
                        config_json={},
                        enabled=True,
                        next_run_at=due_at,
                    )
                )
        db.commit()
        big_id, small_id = big.id, small.id

    published = []

    class FakePublisher:
        def publish(self, task):
            published.append(task)

    # cap=2: у big публикуются только 2 из 5, у small — единственный
    assert publish_due_checks(FakePublisher()) == 3

    with worker_session_factory() as db:
        published_ids = {task.monitor_id for task in published}
        per_org: dict[int, int] = {}
        for monitor in db.scalars(select(Monitor)).all():
            next_run_at = monitor.next_run_at.replace(tzinfo=timezone.utc)
            if monitor.id in published_ids:
                per_org[monitor.org_id] = per_org.get(monitor.org_id, 0) + 1
                assert next_run_at > due_at  # опубликованным сдвинули next_run_at
            else:
                assert next_run_at == due_at  # остальные ждут следующего тика
        assert per_org == {big_id: 2, small_id: 1}
