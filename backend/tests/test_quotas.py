from app.core.config import get_settings
from app.models import Organization, User
from app.services.plans import ensure_default_plans

MONITOR_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def enterprise(monkeypatch):
    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")


def current_org_id(client, headers):
    return client.get("/api/v1/auth/me", headers=headers).json()["organization"]["id"]


def unlock_plan_limits(db_session_factory, org_id):
    """Квотные тесты проверяют org-квоты, а не тарифы: переводим организацию на
    щедрый business, чтобы гейтинг плана (free по умолчанию) не мешал сценарию."""
    with db_session_factory() as db:
        ensure_default_plans(db)
        org = db.get(Organization, org_id)
        org.plan_slug = "business"
        db.commit()


def config_with(*slugs, disabled=()):
    monitors = "\n".join(
        f"  - id: {slug}\n    type: http\n    url: https://example.com\n    interval: 60\n"
        f"    enabled: {'false' if slug in disabled else 'true'}"
        for slug in slugs
    )
    return {"content": f"version: 1\nmonitors:\n{monitors}\n", "format": "yaml"}


def test_patch_current_org_owner_only(client):
    owner = register_and_login(client, "owner@example.com")
    second = register_and_login(client, "second@example.com")
    second_id = client.get("/api/v1/auth/me", headers=second).json()["id"]
    assert (
        client.patch(f"/api/v1/orgs/current/members/{second_id}", json={"role": "admin"}, headers=owner).status_code
        == 200
    )

    # admin недостаточно — только owner
    denied = client.patch("/api/v1/orgs/current", json={"name": "Renamed"}, headers=second)
    assert denied.status_code == 403

    updated = client.patch(
        "/api/v1/orgs/current",
        json={"name": "Renamed", "quota_monitors": 5, "quota_members": 3},
        headers=owner,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Renamed"
    assert body["quota_monitors"] == 5
    assert body["quota_members"] == 3
    assert client.get("/api/v1/auth/me", headers=owner).json()["organization"]["name"] == "Renamed"


def test_monitor_quota_on_create_and_upload(client, db_session_factory, monkeypatch):
    enterprise(monkeypatch)
    owner = register_and_login(client, "owner@example.com")
    unlock_plan_limits(db_session_factory, current_org_id(client, owner))
    assert client.patch("/api/v1/orgs/current", json={"quota_monitors": 1}, headers=owner).status_code == 200

    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201
    denied = client.post("/api/v1/monitors", json={**MONITOR_PAYLOAD, "id": "second"}, headers=owner)
    assert denied.status_code == 403
    assert "quota" in denied.json()["detail"].lower()

    # выключенный монитор квоту не расходует
    assert (
        client.post(
            "/api/v1/monitors", json={**MONITOR_PAYLOAD, "id": "second", "enabled": False}, headers=owner
        ).status_code
        == 201
    )

    # upload: два enabled — сверх квоты, один enabled + один disabled — в пределах
    denied = client.post("/api/v1/config", json=config_with("a", "b"), headers=owner)
    assert denied.status_code == 403
    assert "quota" in denied.json()["detail"].lower()
    assert client.post("/api/v1/config", json=config_with("a", "b", disabled=("b",)), headers=owner).status_code == 200


def test_member_quota_on_add(client, db_session_factory, monkeypatch):
    enterprise(monkeypatch)
    owner = register_and_login(client, "owner@example.com")
    unlock_plan_limits(db_session_factory, current_org_id(client, owner))
    assert client.patch("/api/v1/orgs/current", json={"quota_members": 2}, headers=owner).status_code == 200

    # в SaaS регистрация заводит собственный воркспейс и чужую квоту не расходует
    second = client.post("/api/v1/auth/register", json={"email": "second@example.com", "password": "password123"})
    assert second.status_code == 201

    # приглашение занимает последний слот квоты
    invited = client.post(
        "/api/v1/orgs/current/members", json={"email": "second@example.com", "role": "member"}, headers=owner
    )
    assert invited.status_code == 201

    # следующее приглашение — 403 по квоте участников
    with db_session_factory() as db:
        db.add(User(email="lonely@example.com", hashed_password="x"))
        db.commit()
    denied = client.post(
        "/api/v1/orgs/current/members", json={"email": "lonely@example.com", "role": "member"}, headers=owner
    )
    assert denied.status_code == 403
    assert "quota" in denied.json()["detail"].lower()

    # расширение квоты снова открывает добавление
    assert client.patch("/api/v1/orgs/current", json={"quota_members": 3}, headers=owner).status_code == 200
    assert (
        client.post(
            "/api/v1/orgs/current/members", json={"email": "lonely@example.com", "role": "member"}, headers=owner
        ).status_code
        == 201
    )


def test_null_quota_means_unlimited(client, db_session_factory, monkeypatch):
    enterprise(monkeypatch)
    owner = register_and_login(client, "owner@example.com")
    unlock_plan_limits(db_session_factory, current_org_id(client, owner))

    assert client.patch("/api/v1/orgs/current", json={"quota_monitors": 1}, headers=owner).status_code == 200
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201
    assert client.post("/api/v1/monitors", json={**MONITOR_PAYLOAD, "id": "second"}, headers=owner).status_code == 403

    # снятие квоты (явный null) = безлимит
    cleared = client.patch("/api/v1/orgs/current", json={"quota_monitors": None}, headers=owner)
    assert cleared.status_code == 200
    assert cleared.json()["quota_monitors"] is None
    assert client.post("/api/v1/monitors", json={**MONITOR_PAYLOAD, "id": "second"}, headers=owner).status_code == 201


def test_team_mode_ignores_org_quotas(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "deployment_mode", "team")
    owner = register_and_login(client, "owner@example.com")
    # квоту можно записать, но в team-режиме действуют только глобальные env-лимиты
    assert client.patch("/api/v1/orgs/current", json={"quota_monitors": 0}, headers=owner).status_code == 200
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=owner).status_code == 201
