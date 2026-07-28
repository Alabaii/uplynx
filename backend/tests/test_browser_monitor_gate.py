"""Гейт браузерных сценариев (BROWSER_MONITORS_ENABLED).

У браузерного воркера нет пиннинга адреса: validate_public_url проверяет имя,
а Chromium резолвит его заново и сам. Пока это не закрыто изоляцией воркера,
сценарии выключены — здесь проверяется, что выключены они по-настоящему,
на всех путях, а не только в UI.
"""
import asyncio

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Incident, Monitor

BROWSER_PAYLOAD = {
    "id": "flow",
    "type": "browser",
    "interval": 300,
    "steps": [{"action": "goto", "url": "https://example.com"}],
}
HTTP_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


@pytest.fixture(autouse=True)
def disable_browser_monitors(monkeypatch):
    """Переопределяет общую фикстуру conftest: здесь сценарии выключены."""
    monkeypatch.setattr(get_settings(), "browser_monitors_enabled", False)


def test_meta_reports_browser_monitors_disabled(client):
    assert client.get("/api/v1/meta").json()["browser_monitors_enabled"] is False


def test_create_enabled_browser_monitor_is_rejected(client, auth_headers):
    response = client.post("/api/v1/monitors", json=BROWSER_PAYLOAD, headers=auth_headers)
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


def test_http_monitor_is_unaffected(client, auth_headers):
    assert client.post("/api/v1/monitors", json=HTTP_PAYLOAD, headers=auth_headers).status_code == 201


def test_disabled_browser_monitor_may_exist_but_not_be_enabled(client, auth_headers):
    """Существовать выключённым можно — иначе сломалась бы выгрузка/загрузка конфига."""
    created = client.post(
        "/api/v1/monitors", json={**BROWSER_PAYLOAD, "enabled": False}, headers=auth_headers
    )
    assert created.status_code == 201

    response = client.put("/api/v1/monitors/flow", json={"enabled": True}, headers=auth_headers)
    assert response.status_code == 403


def test_config_upload_rejects_enabled_browser_monitor(client, auth_headers):
    content = (
        "version: 1\n"
        "monitors:\n"
        "  - id: flow\n"
        "    type: browser\n"
        "    interval: 300\n"
        "    enabled: true\n"
        "    steps:\n"
        "      - action: goto\n"
        "        url: https://example.com\n"
    )
    response = client.post(
        "/api/v1/config", json={"content": content, "format": "yaml"}, headers=auth_headers
    )
    assert response.status_code == 403


def test_config_round_trip_survives_with_disabled_browser_monitor(client, auth_headers):
    """Конфиг — источник правды: выгруженный документ обязан загружаться обратно."""
    client.post("/api/v1/monitors", json={**BROWSER_PAYLOAD, "enabled": False}, headers=auth_headers)
    current = client.get("/api/v1/config", headers=auth_headers).json()

    response = client.post(
        "/api/v1/config",
        json={"content": current["content"], "format": current["format"]},
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_scheduler_pauses_enabled_browser_monitors(db_session_factory, monkeypatch):
    """Пре-существующие включённые сценарии гасятся, а не просто не публикуются.

    Иначе монитор остался бы enabled со статусом up, и дашборд показывал бы
    зелёное у сервиса, за которым никто не следит.
    """
    from app.services.incidents import update_incident_for_status_change
    from app.workers import scheduler

    monkeypatch.setattr(scheduler, "SessionLocal", db_session_factory)

    from tests.test_incidents import seed_monitor

    with db_session_factory() as db:
        monitor = seed_monitor(db, slug="flow", org_slug="gate", email="gate@example.com")
        monitor.type = "browser"
        monitor.status = "down"
        db.flush()
        update_incident_for_status_change(db, monitor, "down", "boom")
        db.commit()
        monitor_id = monitor.id

    assert scheduler.pause_browser_monitors_if_disabled() == 1

    with db_session_factory() as db:
        monitor = db.get(Monitor, monitor_id)
        assert monitor.enabled is False
        assert monitor.status == "paused"
        assert monitor.next_run_at is None
        # проверок не будет — открытый инцидент закрыт, иначе он висел бы вечно
        assert db.scalar(select(Incident)).status == "resolved"


def test_scheduler_leaves_http_monitors_alone(db_session_factory, monkeypatch):
    from app.workers import scheduler

    monkeypatch.setattr(scheduler, "SessionLocal", db_session_factory)

    from tests.test_incidents import seed_monitor

    with db_session_factory() as db:
        monitor = seed_monitor(db, slug="site", org_slug="gate2", email="gate2@example.com")
        db.commit()
        monitor_id = monitor.id

    assert scheduler.pause_browser_monitors_if_disabled() == 0
    with db_session_factory() as db:
        assert db.get(Monitor, monitor_id).enabled is True


def test_worker_does_not_launch_chromium_for_queued_task(monkeypatch):
    """Задача могла остаться в durable-очереди с прошлого запуска."""
    from app.schemas import CheckTask
    from app.workers import browser_worker

    launched = []
    monkeypatch.setattr(
        browser_worker, "run_browser_check", lambda *a, **kw: launched.append(True)
    )

    task = CheckTask(
        task_id="stale",
        monitor_id=1,
        type="browser",
        config={"steps": [{"action": "goto", "url": "https://example.com"}]},
        timeout_seconds=30,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    )
    result = asyncio.run(browser_worker.browser_check_with_secrets(task))

    assert launched == []
    assert result["details"]["browser_disabled"] is True


def test_check_now_is_rejected_for_browser_monitor(client, auth_headers, monkeypatch):
    """«Проверить сейчас» публикует задачу мимо шедулера — гейт нужен и здесь.

    Фильтр в выборке шедулера на этот путь не действует: если гашение на старте
    не отработало и монитор остался enabled, одна кнопка отправляла бы задачу
    в очередь в обход выключённой фичи.
    """
    # заводим монитор при включённых сценариях, затем выключаем их
    monkeypatch.setattr(get_settings(), "browser_monitors_enabled", True)
    assert client.post("/api/v1/monitors", json=BROWSER_PAYLOAD, headers=auth_headers).status_code == 201
    monkeypatch.setattr(get_settings(), "browser_monitors_enabled", False)

    published = []

    class FakePublisher:
        def publish(self, task):
            published.append(task)

        def close(self):
            return None

    from app.api.v1.endpoints import monitors as monitors_module

    client.app.dependency_overrides[monitors_module.get_publisher] = lambda: FakePublisher()
    try:
        response = client.post("/api/v1/monitors/flow/check", headers=auth_headers)
    finally:
        client.app.dependency_overrides.pop(monitors_module.get_publisher, None)

    assert response.status_code == 403
    assert published == []


def test_check_now_still_works_for_http_monitor(client, auth_headers):
    """Обратная сторона: HTTP-мониторы кнопкой проверяются как обычно."""
    assert client.post("/api/v1/monitors", json=HTTP_PAYLOAD, headers=auth_headers).status_code == 201

    published = []

    class FakePublisher:
        def publish(self, task):
            published.append(task)

        def close(self):
            return None

    from app.api.v1.endpoints import monitors as monitors_module

    client.app.dependency_overrides[monitors_module.get_publisher] = lambda: FakePublisher()
    try:
        response = client.post("/api/v1/monitors/site/check", headers=auth_headers)
    finally:
        client.app.dependency_overrides.pop(monitors_module.get_publisher, None)

    assert response.status_code == 202
    assert len(published) == 1
