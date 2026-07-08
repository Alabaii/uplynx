import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AuditLog, PasswordResetToken


def register(client, email, password="password123"):
    assert client.post("/api/v1/auth/register", json={"email": email, "password": password}).status_code == 201


def mock_send_email(monkeypatch, sent):
    def fake_send(to, subject, body):
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr("app.api.v1.endpoints.auth.send_email", fake_send)


def extract_token(body):
    return body.split("token=")[1].split()[0]


def test_forgot_password_unknown_email_returns_204_without_token(client, db_session_factory, monkeypatch):
    sent = []
    mock_send_email(monkeypatch, sent)

    response = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    assert response.status_code == 204

    # существование аккаунта не раскрывается: ни письма, ни токена
    assert sent == []
    with db_session_factory() as db:
        assert db.scalar(select(PasswordResetToken)) is None


def test_forgot_password_stores_hash_and_emails_link(client, db_session_factory, monkeypatch):
    register(client, "reset@example.com")
    sent = []
    mock_send_email(monkeypatch, sent)

    assert client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"}).status_code == 204

    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "reset@example.com"
    assert subject == "Reset your PWA Monitor password"
    assert "/reset-password?token=" in body

    token = extract_token(body)
    with db_session_factory() as db:
        row = db.scalar(select(PasswordResetToken))
        assert row is not None
        assert row.token_hash != token  # в БД лежит hash, не сам токен
        assert row.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert row.used_at is None


def test_new_request_invalidates_previous_token(client, monkeypatch):
    register(client, "twice@example.com")
    sent = []
    mock_send_email(monkeypatch, sent)

    client.post("/api/v1/auth/forgot-password", json={"email": "twice@example.com"})
    client.post("/api/v1/auth/forgot-password", json={"email": "twice@example.com"})
    first_token, second_token = extract_token(sent[0][2]), extract_token(sent[1][2])

    stale = client.post(
        "/api/v1/auth/reset-password", json={"token": first_token, "new_password": "newpassword2"}
    )
    assert stale.status_code == 400

    fresh = client.post(
        "/api/v1/auth/reset-password", json={"token": second_token, "new_password": "newpassword2"}
    )
    assert fresh.status_code == 204


def test_reset_password_changes_password_and_token_is_single_use(client, db_session_factory, monkeypatch):
    register(client, "flow@example.com", "oldpassword1")
    sent = []
    mock_send_email(monkeypatch, sent)
    client.post("/api/v1/auth/forgot-password", json={"email": "flow@example.com"})
    token = extract_token(sent[0][2])

    response = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword2"})
    assert response.status_code == 204

    old_login = client.post("/api/v1/auth/login", json={"email": "flow@example.com", "password": "oldpassword1"})
    assert old_login.status_code == 401
    new_login = client.post("/api/v1/auth/login", json={"email": "flow@example.com", "password": "newpassword2"})
    assert new_login.status_code == 200

    # токен одноразовый
    again = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "thirdpassword3"})
    assert again.status_code == 400
    assert again.json()["detail"] == "Invalid or expired token"

    # сброс записан в аудит организации пользователя
    with db_session_factory() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "auth.password_reset"))
        assert entry is not None
        assert entry.entity == "user"


def test_reset_password_expired_token(client, db_session_factory, monkeypatch):
    register(client, "expired@example.com")
    sent = []
    mock_send_email(monkeypatch, sent)
    client.post("/api/v1/auth/forgot-password", json={"email": "expired@example.com"})
    token = extract_token(sent[0][2])

    with db_session_factory() as db:
        row = db.scalar(select(PasswordResetToken))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    response = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword2"})
    assert response.status_code == 400


def test_reset_password_garbage_token_and_weak_password(client):
    garbage = client.post(
        "/api/v1/auth/reset-password", json={"token": "garbage", "new_password": "newpassword2"}
    )
    assert garbage.status_code == 400

    # ограничения пароля — как у регистрации (min 8 символов)
    weak = client.post("/api/v1/auth/reset-password", json={"token": "whatever", "new_password": "short"})
    assert weak.status_code == 422


def test_forgot_password_rate_limited_per_ip(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "forgot_rate_limit_attempts", 2)

    for _ in range(2):
        assert client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 204

    blocked = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
