from sqlalchemy import select

from app.models import AuditLog

MONITOR_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}
TELEGRAM_PAYLOAD = {"bot_token": "123456:AAAbbbCCCdddEEE", "chat_id": "42", "alert_scopes": ["down"]}
EMPTY_CONFIG = {"content": "version: 1\nmonitors: []\n", "format": "yaml"}


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def user_id_of(client, headers):
    return client.get("/api/v1/auth/me", headers=headers).json()["id"]


def audit_rows(db_session_factory, action):
    with db_session_factory() as db:
        return db.scalars(select(AuditLog).where(AuditLog.action == action)).all()


def test_monitor_create_writes_audit_event(client, auth_headers, db_session_factory):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201

    rows = audit_rows(db_session_factory, "monitor.create")
    assert len(rows) == 1
    entry = rows[0]
    assert entry.entity == "monitor"
    assert entry.entity_id == "site"
    assert entry.payload == {"name": "site", "type": "http"}
    assert entry.org_id is not None
    assert entry.user_id is not None


def test_failed_monitor_create_writes_no_audit_event(client, auth_headers, db_session_factory):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201
    # дубликат → 409, транзакция откатывается вместе с аудит-записью
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 409

    assert len(audit_rows(db_session_factory, "monitor.create")) == 1


def test_config_upload_writes_audit_event(client, auth_headers, db_session_factory):
    assert client.post("/api/v1/config", json=EMPTY_CONFIG, headers=auth_headers).status_code == 200

    rows = audit_rows(db_session_factory, "config.upload")
    assert len(rows) == 1
    assert rows[0].entity == "config"
    assert rows[0].payload == {"version": 1}


def test_role_change_writes_audit_event(client, db_session_factory):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")
    second_id = user_id_of(client, second)

    response = client.patch(
        f"/api/v1/orgs/current/members/{second_id}", json={"role": "admin"}, headers=owner
    )
    assert response.status_code == 200

    rows = audit_rows(db_session_factory, "member.role_change")
    assert len(rows) == 1
    assert rows[0].entity_id == str(second_id)
    assert rows[0].payload == {"member_email": "second@example.com", "role": "admin"}


def test_telegram_connect_audit_has_no_token(client, auth_headers, db_session_factory):
    assert client.post("/api/v1/telegram/connect", json=TELEGRAM_PAYLOAD, headers=auth_headers).status_code == 200

    rows = audit_rows(db_session_factory, "telegram.connect")
    assert len(rows) == 1
    assert rows[0].payload == {"chat_id": "42"}
    assert TELEGRAM_PAYLOAD["bot_token"] not in str(rows[0].payload)


def test_audit_endpoint_requires_admin_and_joins_actor(client):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")  # member по умолчанию

    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201

    # member — 403
    assert client.get("/api/v1/orgs/current/audit", headers=second).status_code == 403

    response = client.get("/api/v1/orgs/current/audit", headers=owner)
    assert response.status_code == 200
    events = response.json()
    # два auth.register + monitor.create, отсортированы по created_at DESC
    actions = [event["action"] for event in events]
    assert actions[0] == "monitor.create"
    assert actions.count("auth.register") == 2
    newest = events[0]
    assert newest["actor_email"] == "owner@example.com"
    assert newest["entity_id"] == "site"
    assert newest["payload"] == {"name": "site", "type": "http"}
    assert "created_at" in newest


def test_audit_endpoint_limit_and_offset(client, auth_headers):
    for index in range(3):
        payload = {**MONITOR_PAYLOAD, "id": f"site-{index}"}
        assert client.post("/api/v1/monitors", json=payload, headers=auth_headers).status_code == 201

    first_page = client.get("/api/v1/orgs/current/audit?limit=2", headers=auth_headers).json()
    assert len(first_page) == 2
    second_page = client.get("/api/v1/orgs/current/audit?limit=2&offset=2", headers=auth_headers).json()
    assert {event["id"] for event in first_page}.isdisjoint({event["id"] for event in second_page})

    # limit валидируется: max 200
    assert client.get("/api/v1/orgs/current/audit?limit=500", headers=auth_headers).status_code == 422
