"""Изоляция арендаторов при публичной регистрации.

В SaaS-режиме каждый регистрирующийся получает собственный воркспейс. До этого
все попадали в общую организацию «default» ролью member: посторонний клиент
платформы видел чужие мониторы, менял их URL и удалял их.
"""
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Organization, OrgMember, User
from app.services.orgs import DEFAULT_ORG_SLUG


@pytest.fixture()
def saas(monkeypatch):
    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")


def signup(client, email, password="password123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_saas_signup_creates_own_workspace(client, saas, db_session_factory):
    headers = signup(client, "alice@alpha.example")

    organization = client.get("/api/v1/auth/me", headers=headers).json()["organization"]
    assert organization["role"] == "owner"
    assert organization["slug"] != DEFAULT_ORG_SLUG

    with db_session_factory() as db:
        assert db.scalar(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG)) is None


def test_saas_signups_do_not_share_a_workspace(client, saas):
    alice = signup(client, "alice@alpha.example")
    bob = signup(client, "bob@beta.example")

    created = client.post(
        "/api/v1/monitors",
        json={"id": "alice-api", "type": "http", "url": "https://alice.example", "interval": 300},
        headers=alice,
    )
    assert created.status_code == 201

    assert client.get("/api/v1/monitors", headers=bob).json() == []
    assert client.get("/api/v1/monitors/alice-api", headers=bob).status_code == 404
    assert client.put("/api/v1/monitors/alice-api", json={"url": "https://evil.example"}, headers=bob).status_code == 404
    assert client.delete("/api/v1/monitors/alice-api", headers=bob).status_code == 404
    assert client.get("/api/v1/history", headers=bob).json() == []
    # монитор владельца не пострадал
    assert client.get("/api/v1/monitors/alice-api", headers=alice).json()["url"] == "https://alice.example"


def test_saas_secrets_are_not_visible_to_other_workspaces(client, saas):
    alice = signup(client, "alice@alpha.example")
    bob = signup(client, "bob@beta.example")

    stored = client.put(
        "/api/v1/secrets/ALICE_TOKEN", json={"name": "ALICE_TOKEN", "value": "hunter2"}, headers=alice
    )
    assert stored.status_code == 200

    assert client.get("/api/v1/secrets", headers=bob).json() == []
    assert [s["name"] for s in client.get("/api/v1/secrets", headers=alice).json()] == ["ALICE_TOKEN"]


def test_saas_slug_collision_gets_unique_workspace(client, saas, db_session_factory):
    # одинаковая локальная часть на разных доменах — слаг обязан остаться уникальным
    signup(client, "admin@alpha.example")
    signup(client, "admin@beta.example")

    with db_session_factory() as db:
        slugs = list(db.scalars(select(Organization.slug).order_by(Organization.id)))
    assert slugs[0] == "admin"
    assert slugs[1].startswith("admin-")
    assert len(set(slugs)) == 2


def test_team_mode_still_shares_the_default_org(client, db_session_factory):
    # self-hosted редакция: инсталляция обслуживает одну команду — поведение прежнее
    signup(client, "first@example.com")
    signup(client, "second@example.com")

    with db_session_factory() as db:
        org = db.scalar(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG))
        assert org is not None
        roles = {
            db.scalar(select(User.email).where(User.id == member.user_id)): member.role
            for member in db.scalars(select(OrgMember).where(OrgMember.org_id == org.id))
        }
    assert roles == {"first@example.com": "owner", "second@example.com": "member"}


# --- потолок на самостоятельное создание организаций -----------------------------------------------


def create_org(client, headers, slug):
    return client.post("/api/v1/orgs", headers=headers, json={"name": slug, "slug": slug})


def test_owned_org_limit_blocks_free_workspace_farming(client, saas, monkeypatch):
    """Лимиты тарифа считаются на организацию: без потолка на их число клиент
    бесплатного плана получал бы сколько угодно бесплатных воркспейсов."""
    monkeypatch.setattr(get_settings(), "max_owned_orgs_per_user", 3)
    headers = signup(client, "farmer@alpha.example")

    # регистрация уже дала персональный воркспейс (owner) — остаётся два
    assert create_org(client, headers, "second-org").status_code == 201
    assert create_org(client, headers, "third-org").status_code == 201

    response = create_org(client, headers, "fourth-org")
    assert response.status_code == 403
    assert "limit 3" in response.json()["detail"]


def test_membership_in_someone_elses_org_does_not_count(client, saas, monkeypatch):
    """Потолок считает только организации, где пользователь owner."""
    monkeypatch.setattr(get_settings(), "max_owned_orgs_per_user", 2)
    owner = signup(client, "owner@alpha.example")
    guest = signup(client, "guest@beta.example")
    client.post("/api/v1/orgs/current/members", headers=owner, json={"email": "guest@beta.example", "role": "admin"})

    # у гостя свой воркспейс + членство в чужом: создать ещё один он всё равно может
    assert create_org(client, guest, "guest-second").status_code == 201
    assert create_org(client, guest, "guest-third").status_code == 403
