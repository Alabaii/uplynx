from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import RefreshToken

CREDS = {"email": "user@example.com", "password": "password123"}


def register_and_login(client, email="user@example.com"):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    return client.post("/api/v1/auth/login", json=payload).json()


def test_login_returns_refresh_token(client):
    tokens = register_and_login(client)
    assert tokens["access_token"]
    assert tokens["refresh_token"]


def test_refresh_rotates_tokens(client):
    tokens = register_and_login(client)

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # новый access работает
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
    assert me.status_code == 200

    # старый refresh отозван ротацией
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401


def test_reuse_of_rotated_token_revokes_all_sessions(client):
    tokens = register_and_login(client)
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()

    # предъявление уже отозванного токена — кража: гасятся ВСЕ сессии, включая свежую
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401


def test_expired_refresh_rejected(client, db_session_factory):
    tokens = register_and_login(client)
    with db_session_factory() as db:
        session = db.scalar(select(RefreshToken))
        session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()

    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_garbage_refresh_rejected(client):
    register_and_login(client)
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"}).status_code == 401


def test_logout_revokes_session(client):
    tokens = register_and_login(client)

    assert client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    # повторный логаут идемпотентен
    assert client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204


def test_password_reset_revokes_all_sessions(client, db_session_factory, monkeypatch):
    from app.core.config import get_settings

    tokens = register_and_login(client)

    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.test")
    sent = []
    monkeypatch.setattr("app.api.v1.endpoints.auth.send_email", lambda to, s, b: sent.append(b) or True)
    assert client.post("/api/v1/auth/forgot-password", json={"email": CREDS["email"]}).status_code == 204
    reset_token = sent[0].split("token=")[1].split()[0].strip()

    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "new-password-123"}
        ).status_code
        == 204
    )

    # все refresh-сессии погашены сбросом пароля
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_refresh_keeps_switched_org(client):
    owner = register_and_login(client, "owner@example.com")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}

    # вторая организация (enterprise-фича доступна и в тестах через API)
    created = client.post("/api/v1/orgs", json={"name": "Second", "slug": "second"}, headers=headers)
    if created.status_code != 201:
        # team-режим без создания организаций — сценарий не применим
        return
    second_id = created.json()["id"]

    switched = client.post(
        f"/api/v1/orgs/{second_id}/switch",
        json={"refresh_token": owner["refresh_token"]},
        headers=headers,
    )
    assert switched.status_code == 200

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": owner["refresh_token"]}).json()
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refreshed['access_token']}"})
    # после refresh активная организация осталась переключённой, не откатилась к первой
    assert me.json()["organization"]["id"] == second_id
