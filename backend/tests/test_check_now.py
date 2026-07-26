from datetime import datetime, timedelta, timezone

import pika
import pytest
from sqlalchemy import select

from app.api.v1.endpoints.monitors import get_publisher
from app.main import app
from app.models import AuditLog

MONITOR_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def user_id_of(client, headers):
    return client.get("/api/v1/auth/me", headers=headers).json()["id"]


class FakePublisher:
    def __init__(self, error=None):
        self.tasks = []
        self.closed = False
        self.error = error

    def publish(self, task):
        if self.error:
            raise self.error
        self.tasks.append(task)

    def close(self):
        self.closed = True


@pytest.fixture()
def fake_publisher(client):
    publisher = FakePublisher()
    app.dependency_overrides[get_publisher] = lambda: publisher
    yield publisher
    app.dependency_overrides.pop(get_publisher, None)


def test_check_now_queues_task(client, auth_headers, fake_publisher, db_session_factory):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201

    response = client.post("/api/v1/monitors/site/check", headers=auth_headers)
    assert response.status_code == 202
    body = response.json()
    assert body["queued"] is True
    assert body["task_id"]

    assert len(fake_publisher.tasks) == 1
    task = fake_publisher.tasks[0]
    assert task.task_id == body["task_id"]
    assert task.type == "http"
    assert task.url == "https://example.com"
    assert fake_publisher.closed is True

    with db_session_factory() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "monitor.check_now"))
        assert entry is not None
        assert entry.entity_id == "site"
        assert entry.payload["task_id"] == body["task_id"]


def test_check_now_unknown_monitor_404(client, auth_headers, fake_publisher):
    assert client.post("/api/v1/monitors/ghost/check", headers=auth_headers).status_code == 404
    assert fake_publisher.tasks == []


def test_check_now_disabled_monitor_409(client, auth_headers, fake_publisher):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201
    # пауза — это enabled=false, а не удаление (оно теперь архивирует)
    assert client.put("/api/v1/monitors/site", json={"enabled": False}, headers=auth_headers).status_code == 200

    response = client.post("/api/v1/monitors/site/check", headers=auth_headers)
    assert response.status_code == 409
    assert fake_publisher.tasks == []


def test_check_now_archived_monitor_404(client, auth_headers, fake_publisher):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201
    assert client.delete("/api/v1/monitors/site", headers=auth_headers).status_code == 204

    # архивного монитора для API не существует: слаг мог быть занят заново
    response = client.post("/api/v1/monitors/site/check", headers=auth_headers)
    assert response.status_code == 404
    assert fake_publisher.tasks == []


def test_check_now_in_maintenance_409(client, auth_headers, fake_publisher):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201
    starts = datetime.now(timezone.utc) - timedelta(minutes=5)
    ends = starts + timedelta(hours=1)
    window = {"monitor_id": "site", "starts_at": starts.isoformat(), "ends_at": ends.isoformat()}
    assert client.post("/api/v1/maintenance", json=window, headers=auth_headers).status_code == 201

    response = client.post("/api/v1/monitors/site/check", headers=auth_headers)
    assert response.status_code == 409
    assert fake_publisher.tasks == []


def test_check_now_viewer_forbidden(client, fake_publisher):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")
    second_id = user_id_of(client, second)
    assert (
        client.patch(
            f"/api/v1/orgs/current/members/{second_id}", json={"role": "viewer"}, headers=owner
        ).status_code
        == 200
    )
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201

    assert client.post("/api/v1/monitors/site/check", headers=second).status_code == 403
    assert fake_publisher.tasks == []


def test_check_now_queue_unavailable_503(client, auth_headers):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201
    broken = FakePublisher(error=pika.exceptions.AMQPConnectionError("no rabbit"))
    app.dependency_overrides[get_publisher] = lambda: broken
    try:
        response = client.post("/api/v1/monitors/site/check", headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_publisher, None)
    assert response.status_code == 503
    assert broken.closed is True
