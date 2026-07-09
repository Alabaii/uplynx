import hashlib

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import EmailVerificationToken, User

REGISTER = {"email": "new@example.com", "password": "password123"}


@pytest.fixture()
def smtp_on(monkeypatch):
    # гейт верификации активен только при настроенном SMTP
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.test")
    return monkeypatch


@pytest.fixture()
def captured_email(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.send_email",
        lambda to, subject, body: sent.append((to, subject, body)) or True,
    )
    return sent


def register(client):
    return client.post("/api/v1/auth/register", json=REGISTER)


def login(client):
    return client.post("/api/v1/auth/login", json=REGISTER)


def verify_token_for(db_session_factory, email):
    """Разворачивает сырой токен нельзя (в БД только hash) — берём hash напрямую для API."""
    with db_session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        token = db.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
        )
        return token.token_hash


# --- гейт активен (SMTP настроен) ---------------------------------------------------------------


def test_register_sends_verification_and_blocks_login(client, smtp_on, captured_email):
    assert register(client).status_code == 201
    assert len(captured_email) == 1
    to, subject, body = captured_email[0]
    assert to == "new@example.com"
    assert "verify" in subject.lower()
    assert "/verify-email?token=" in body

    blocked = login(client)
    assert blocked.status_code == 403
    assert "not verified" in blocked.json()["detail"].lower()


def test_verify_email_unlocks_login(client, smtp_on, captured_email):
    register(client)
    raw_token = captured_email[0][2].split("token=")[1].split()[0].strip()

    verified = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verified.status_code == 204

    ok = login(client)
    assert ok.status_code == 200
    assert ok.json()["access_token"]


def test_verify_email_rejects_bad_and_used_token(client, smtp_on, captured_email):
    register(client)
    raw_token = captured_email[0][2].split("token=")[1].split()[0].strip()

    assert client.post("/api/v1/auth/verify-email", json={"token": "garbage"}).status_code == 400
    assert client.post("/api/v1/auth/verify-email", json={"token": raw_token}).status_code == 204
    # повторное использование того же токена — уже отмечен used_at
    assert client.post("/api/v1/auth/verify-email", json={"token": raw_token}).status_code == 400


def test_resend_verification_issues_new_email(client, smtp_on, captured_email):
    register(client)
    assert len(captured_email) == 1

    resend = client.post("/api/v1/auth/resend-verification", json={"email": "new@example.com"})
    assert resend.status_code == 204
    assert len(captured_email) == 2
    assert "/verify-email?token=" in captured_email[1][2]


def test_resend_for_unknown_or_verified_is_silent(client, smtp_on, captured_email):
    # неизвестный адрес — 204 без письма (не раскрываем существование)
    assert client.post("/api/v1/auth/resend-verification", json={"email": "ghost@example.com"}).status_code == 204
    assert captured_email == []

    register(client)
    raw_token = captured_email[0][2].split("token=")[1].split()[0].strip()
    client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    before = len(captured_email)
    # уже верифицирован — повторное письмо не шлём
    assert client.post("/api/v1/auth/resend-verification", json={"email": "new@example.com"}).status_code == 204
    assert len(captured_email) == before


def test_me_reports_verification_status(client, smtp_on, captured_email):
    register(client)
    raw_token = captured_email[0][2].split("token=")[1].split()[0].strip()
    client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    token = login(client).json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email_verified"] is True


# --- гейт выключен (SMTP не настроен) — обратная совместимость -----------------------------------


def test_without_smtp_no_verification_required(client, captured_email):
    # SMTP не настроен: письмо не шлётся, вход сразу доступен, /me показывает verified
    assert register(client).status_code == 201
    assert captured_email == []

    ok = login(client)
    assert ok.status_code == 200
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"})
    assert me.json()["email_verified"] is True
