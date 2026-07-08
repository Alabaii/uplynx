from app.models import User

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


def set_role(client, owner_headers, user_id, role):
    response = client.patch(
        f"/api/v1/orgs/current/members/{user_id}", json={"role": role}, headers=owner_headers
    )
    assert response.status_code == 200
    return response


def test_viewer_cannot_write_member_can(client):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")  # member по умолчанию
    second_id = user_id_of(client, second)

    set_role(client, owner, second_id, "viewer")

    # viewer: чтение доступно, запись — нет
    assert client.get("/api/v1/monitors", headers=second).status_code == 200
    assert client.get("/api/v1/config", headers=second).status_code == 200
    assert client.get("/api/v1/orgs/current/members", headers=second).status_code == 200
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=second).status_code == 403
    assert client.post("/api/v1/config", json=EMPTY_CONFIG, headers=second).status_code == 403

    # member: CRUD мониторов и конфиг снова доступны
    set_role(client, owner, second_id, "member")
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=second).status_code == 201
    assert client.post("/api/v1/config", json=EMPTY_CONFIG, headers=second).status_code == 200


def test_member_cannot_rollback_or_telegram_admin_can(client):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")
    second_id = user_id_of(client, second)

    assert client.post("/api/v1/config", json=EMPTY_CONFIG, headers=owner).status_code == 200

    assert client.post("/api/v1/config/rollback", json={"version": 1}, headers=second).status_code == 403
    assert client.post("/api/v1/telegram/connect", json=TELEGRAM_PAYLOAD, headers=second).status_code == 403
    assert client.post("/api/v1/telegram/test", headers=second).status_code == 403
    # читать состояние интеграции может любой член
    assert client.get("/api/v1/telegram", headers=second).status_code == 200

    set_role(client, owner, second_id, "admin")
    assert client.post("/api/v1/config/rollback", json={"version": 1}, headers=second).status_code == 200
    assert client.post("/api/v1/telegram/connect", json=TELEGRAM_PAYLOAD, headers=second).status_code == 200


def test_owner_cannot_be_demoted_or_removed(client):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")
    owner_id = user_id_of(client, owner)
    second_id = user_id_of(client, second)
    set_role(client, owner, second_id, "admin")

    assert (
        client.patch(f"/api/v1/orgs/current/members/{owner_id}", json={"role": "member"}, headers=second).status_code
        == 403
    )
    assert client.delete(f"/api/v1/orgs/current/members/{owner_id}", headers=second).status_code == 403
    # назначить owner нельзя — передача владения вне скоупа
    assert (
        client.patch(f"/api/v1/orgs/current/members/{second_id}", json={"role": "owner"}, headers=owner).status_code
        == 422
    )
    # нельзя удалить самого себя
    assert client.delete(f"/api/v1/orgs/current/members/{second_id}", headers=second).status_code == 400


def test_add_member_by_email(client, db_session_factory):
    owner = register_and_login(client, "owner@example.com")

    # зарегистрированный пользователь без членства в организации
    with db_session_factory() as db:
        db.add(User(email="lonely@example.com", hashed_password="x"))
        db.commit()

    missing = client.post(
        "/api/v1/orgs/current/members", json={"email": "ghost@example.com", "role": "member"}, headers=owner
    )
    assert missing.status_code == 404

    as_owner = client.post(
        "/api/v1/orgs/current/members", json={"email": "lonely@example.com", "role": "owner"}, headers=owner
    )
    assert as_owner.status_code == 422

    added = client.post(
        "/api/v1/orgs/current/members", json={"email": "lonely@example.com", "role": "viewer"}, headers=owner
    )
    assert added.status_code == 201
    assert added.json()["role"] == "viewer"

    duplicate = client.post(
        "/api/v1/orgs/current/members", json={"email": "lonely@example.com", "role": "member"}, headers=owner
    )
    assert duplicate.status_code == 409

    members = client.get("/api/v1/orgs/current/members", headers=owner).json()
    assert {m["email"]: m["role"] for m in members} == {"owner@example.com": "owner", "lonely@example.com": "viewer"}


def test_member_management_requires_admin(client):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")
    owner_id = user_id_of(client, owner)

    assert (
        client.post(
            "/api/v1/orgs/current/members", json={"email": "owner@example.com", "role": "member"}, headers=second
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/api/v1/orgs/current/members/{owner_id}", json={"role": "member"}, headers=second).status_code
        == 403
    )
    assert client.delete(f"/api/v1/orgs/current/members/{owner_id}", headers=second).status_code == 403


def test_removed_member_loses_access(client):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")
    second_id = user_id_of(client, second)

    assert client.delete(f"/api/v1/orgs/current/members/{second_id}", headers=owner).status_code == 204
    assert client.get("/api/v1/monitors", headers=second).status_code == 403


def test_list_orgs_create_org_and_switch(client, monkeypatch):
    owner = register_and_login(client, "owner@example.com")

    orgs = client.get("/api/v1/orgs", headers=owner).json()
    assert len(orgs) == 1
    assert orgs[0]["slug"] == "default"
    assert orgs[0]["role"] == "owner"

    # team-режим: создание организаций закрыто
    forbidden = client.post("/api/v1/orgs", json={"name": "Second team", "slug": "second"}, headers=owner)
    assert forbidden.status_code == 403
    assert "enterprise" in forbidden.json()["detail"]

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")
    created = client.post("/api/v1/orgs", json={"name": "Second team", "slug": "second"}, headers=owner)
    assert created.status_code == 201
    assert created.json()["role"] == "owner"
    second_org_id = created.json()["id"]

    duplicate = client.post("/api/v1/orgs", json={"name": "Another", "slug": "second"}, headers=owner)
    assert duplicate.status_code == 409

    assert len(client.get("/api/v1/orgs", headers=owner).json()) == 2

    switched = client.post(f"/api/v1/orgs/{second_org_id}/switch", headers=owner)
    assert switched.status_code == 200
    switched_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=switched_headers).json()["organization"]["slug"] == "second"

    # переключиться в чужую организацию нельзя
    outsider = register_and_login(client, "outsider@example.com")
    assert client.post(f"/api/v1/orgs/{second_org_id}/switch", headers=outsider).status_code == 403
