from sqlalchemy import select

from app.models import ConfigVersion, Monitor, Organization, OrgMember, TelegramIntegration, User
from app.services.orgs import DEFAULT_ORG_NAME, DEFAULT_ORG_SLUG


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_creates_org_membership(client, db_session_factory):
    client.post("/api/v1/auth/register", json={"email": "first@example.com", "password": "password123"})
    client.post("/api/v1/auth/register", json={"email": "second@example.com", "password": "password123"})

    with db_session_factory() as db:
        org = db.scalar(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG))
        assert org is not None
        assert org.name == DEFAULT_ORG_NAME

        first = db.scalar(select(User).where(User.email == "first@example.com"))
        second = db.scalar(select(User).where(User.email == "second@example.com"))
        first_member = db.scalar(select(OrgMember).where(OrgMember.user_id == first.id))
        second_member = db.scalar(select(OrgMember).where(OrgMember.user_id == second.id))
        assert first_member.org_id == org.id
        assert first_member.role == "owner"
        assert second_member.org_id == org.id
        assert second_member.role == "member"


def test_created_entities_get_default_org_id(client, auth_headers, db_session_factory):
    created = client.post(
        "/api/v1/monitors",
        json={"id": "site", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    assert created.status_code == 201

    connected = client.post(
        "/api/v1/telegram/connect",
        json={"bot_token": "123456:AAAbbbCCCdddEEE", "chat_id": "42", "alert_scopes": ["down"]},
        headers=auth_headers,
    )
    assert connected.status_code == 200

    with db_session_factory() as db:
        org = db.scalar(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG))
        monitor = db.scalar(select(Monitor).where(Monitor.slug == "site"))
        config_version = db.scalar(select(ConfigVersion))
        integration = db.scalar(select(TelegramIntegration))
        assert monitor.org_id == org.id
        assert config_version.org_id == org.id
        assert integration.org_id == org.id


def test_me_returns_organization(client, auth_headers):
    body = client.get("/api/v1/auth/me", headers=auth_headers).json()
    organization = body["organization"]
    assert organization["name"] == DEFAULT_ORG_NAME
    assert organization["slug"] == DEFAULT_ORG_SLUG
    assert organization["role"] == "owner"
    assert isinstance(organization["id"], int)
