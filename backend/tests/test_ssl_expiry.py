import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import encrypt_secret
from app.models import Monitor, Organization, TelegramIntegration, User
from app.schemas import CheckTask
from app.services.alerting import ssl_threshold_to_alert
from app.services.checks import fetch_ssl_expiry, parse_cert_not_after, ssl_details
from app.workers.base import persist_result


# --- разбор сертификата -------------------------------------------------------------------------


def test_parse_cert_not_after():
    parsed = parse_cert_not_after("Jun  1 12:00:00 2027 GMT")
    assert parsed == datetime(2027, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_fetch_ssl_expiry_skips_non_https():
    assert fetch_ssl_expiry("http://example.com") is None
    assert fetch_ssl_expiry("not-a-url") is None


def test_fetch_ssl_expiry_does_not_connect_to_private_targets(monkeypatch):
    """Сертификат снимается отдельным соединением мимо httpx-хука — адрес проверяем сами."""
    attempted = []

    def refuse(*args, **kwargs):
        attempted.append(args)
        raise AssertionError("connection must not be attempted for a private target")

    monkeypatch.setattr("app.services.checks.socket.create_connection", refuse)

    assert fetch_ssl_expiry("https://127.0.0.1") is None
    assert fetch_ssl_expiry("https://169.254.169.254") is None
    assert attempted == []


def test_ssl_details_computes_days_left():
    assert ssl_details(None) is None
    info = ssl_details(datetime.now(timezone.utc) + timedelta(days=10, hours=1))
    assert info["days_left"] == 10
    assert "expires_at" in info


# --- пороги -------------------------------------------------------------------------------------


def test_ssl_threshold_no_alert_far_from_expiry():
    assert ssl_threshold_to_alert(90, None) is None
    assert ssl_threshold_to_alert(31, None) is None


def test_ssl_threshold_picks_tightest_crossed():
    assert ssl_threshold_to_alert(30, None) == 30
    assert ssl_threshold_to_alert(10, None) == 14
    assert ssl_threshold_to_alert(5, None) == 7
    assert ssl_threshold_to_alert(0, None) == 1
    assert ssl_threshold_to_alert(-5, None) == 1


def test_ssl_threshold_not_repeated_and_escalates():
    # по порогу 14 уже алертили: 10 дней — тихо, 6 дней — эскалация на порог 7
    assert ssl_threshold_to_alert(10, 14) is None
    assert ssl_threshold_to_alert(6, 14) == 7
    assert ssl_threshold_to_alert(6, 7) is None
    assert ssl_threshold_to_alert(1, 7) == 1


# --- persist_result -----------------------------------------------------------------------------


@pytest.fixture()
def worker_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.workers.base.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def seed_monitor(session_factory, ssl_alerted_days=None):
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
            status="up",
            url="https://example.com",
            interval=60,
            config_json={},
            enabled=True,
            ssl_alerted_days=ssl_alerted_days,
        )
        db.add(monitor)
        db.add(
            TelegramIntegration(
                user_id=user.id,
                org_id=org.id,
                bot_token_secret=encrypt_secret("123456:secret-token"),
                chat_id="42",
                alert_scopes=["down", "recovered", "ssl"],
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


def up_result_with_ssl(days_left):
    expires_at = datetime.now(timezone.utc) + timedelta(days=days_left, hours=1)
    return {
        "status": "up",
        "response_time_ms": 10,
        "error": None,
        "details": {"status_code": 200, "ssl": {"expires_at": expires_at.isoformat(), "days_left": days_left}},
    }


def test_ssl_alert_sent_once_per_threshold(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory)
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "s1"), up_result_with_ssl(10)))
    assert len(calls) == 1
    assert "[ssl]" in calls[0]
    assert "expires in 10 day(s)" in calls[0]

    with worker_session_factory() as db:
        monitor = db.get(Monitor, monitor_id)
        assert monitor.ssl_expires_at is not None
        assert monitor.ssl_alerted_days == 14

    # следующая проверка с тем же сроком — алерт не дублируется
    asyncio.run(persist_result(make_task(monitor_id, "s2"), up_result_with_ssl(10)))
    assert len(calls) == 1

    # срок стал острее — эскалация на порог 1
    asyncio.run(persist_result(make_task(monitor_id, "s3"), up_result_with_ssl(1)))
    assert len(calls) == 2
    assert "expires in 1 day(s)" in calls[1]


def test_ssl_state_reset_after_renewal(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory, ssl_alerted_days=7)
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "s1"), up_result_with_ssl(90)))
    assert calls == []
    with worker_session_factory() as db:
        assert db.get(Monitor, monitor_id).ssl_alerted_days is None


def test_ssl_ignored_without_details(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory)
    calls = capture_telegram(monkeypatch)

    asyncio.run(
        persist_result(
            make_task(monitor_id, "s1"),
            {"status": "up", "response_time_ms": 10, "error": None, "details": {"status_code": 200}},
        )
    )
    assert calls == []
    with worker_session_factory() as db:
        monitor = db.get(Monitor, monitor_id)
        assert monitor.ssl_expires_at is None
        assert monitor.ssl_alerted_days is None


def test_ssl_alert_respects_telegram_scopes(worker_session_factory, monkeypatch):
    monitor_id = seed_monitor(worker_session_factory)
    with worker_session_factory() as db:
        integration = db.scalar(select(TelegramIntegration))
        integration.alert_scopes = ["down", "recovered"]  # без ssl
        db.commit()
    calls = capture_telegram(monkeypatch)

    asyncio.run(persist_result(make_task(monitor_id, "s1"), up_result_with_ssl(5)))
    assert calls == []  # telegram-канал отфильтрован по scope
    with worker_session_factory() as db:
        # состояние всё равно зафиксировано — push/email каналы это уже получили
        assert db.get(Monitor, monitor_id).ssl_alerted_days == 7


# --- API ----------------------------------------------------------------------------------------


def test_monitor_read_exposes_ssl_days_left(client, auth_headers, db_session_factory):
    payload = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}
    assert client.post("/api/v1/monitors", json=payload, headers=auth_headers).status_code == 201

    with db_session_factory() as db:
        monitor = db.scalar(select(Monitor))
        monitor.ssl_expires_at = datetime.now(timezone.utc) + timedelta(days=9, hours=2)
        db.commit()

    body = client.get("/api/v1/monitors/site", headers=auth_headers).json()
    assert body["ssl_days_left"] == 9
    assert body["ssl_expires_at"] is not None


# --- периодичность снятия сертификата ------------------------------------------------------------


def make_monitor(url="https://example.com", monitor_type="http", ssl_checked_at=None):
    return Monitor(
        id=1,
        user_id=1,
        org_id=1,
        slug="site",
        name="Site",
        type=monitor_type,
        status="up",
        url=url,
        interval=60,
        config_json={},
        enabled=True,
        ssl_checked_at=ssl_checked_at,
    )


def test_ssl_refresh_due_only_for_https_http_monitors():
    from app.services.queue import ssl_refresh_due

    now = datetime.now(timezone.utc)
    assert ssl_refresh_due(make_monitor(), now) is True
    assert ssl_refresh_due(make_monitor(url="http://example.com"), now) is False
    assert ssl_refresh_due(make_monitor(url=None, monitor_type="browser"), now) is False


def test_ssl_refresh_due_not_more_than_once_a_day():
    from app.services.queue import SSL_REFRESH_INTERVAL, ssl_refresh_due

    now = datetime.now(timezone.utc)
    assert ssl_refresh_due(make_monitor(ssl_checked_at=now - timedelta(minutes=5)), now) is False
    assert ssl_refresh_due(make_monitor(ssl_checked_at=now - SSL_REFRESH_INTERVAL), now) is True
    # sqlite отдаёт naive datetime — сравнение не должно падать
    naive = (now - SSL_REFRESH_INTERVAL - timedelta(hours=1)).replace(tzinfo=None)
    assert ssl_refresh_due(make_monitor(ssl_checked_at=naive), now) is True


def test_http_check_skips_certificate_when_not_requested(monkeypatch):
    """Сертификат снимается отдельным соединением — без просьбы его не должно быть."""
    import httpx

    from app.services import checks

    def refuse(*args, **kwargs):
        raise AssertionError("certificate must not be fetched when collect_ssl is False")

    monkeypatch.setattr(checks, "fetch_ssl_expiry", refuse)

    async def fake_fetch(client, url, allow_private):
        return httpx.Response(200, content=b"ok", request=httpx.Request("GET", url)), url

    monkeypatch.setattr(checks, "fetch_following_redirects", fake_fetch)

    task = CheckTask(
        task_id="no-ssl",
        monitor_id=1,
        type="http",
        url="https://example.com",
        config={},
        created_at=datetime.now(timezone.utc),
        collect_ssl=False,
    )
    result = asyncio.run(checks.run_http_check(task))
    assert result["status"] == "up"
    assert "ssl" not in result["details"]
