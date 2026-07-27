from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import EmailVerificationToken, PasswordResetToken, RefreshToken, User
from app.services.retention import purge_expired_tokens


def seed_user(db, email="user@example.com") -> int:
    user = User(email=email, hashed_password="x")
    db.add(user)
    db.flush()
    return user.id


def add_refresh(db, user_id: int, token_hash: str, expires_in: timedelta, revoked: bool = False) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=now + expires_in,
            revoked_at=now - timedelta(days=1) if revoked else None,
        )
    )


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_purge_removes_only_expired_tokens(db_session_factory):
    with db_session_factory() as db:
        user_id = seed_user(db)
        now = datetime.now(timezone.utc)
        add_refresh(db, user_id, "live", timedelta(days=30))
        add_refresh(db, user_id, "expired", -timedelta(days=1))
        # отозванный, но ещё не истёкший: на нём держится детект кражи
        add_refresh(db, user_id, "revoked-fresh", timedelta(days=30), revoked=True)
        add_refresh(db, user_id, "revoked-expired", -timedelta(hours=1), revoked=True)
        db.add(
            PasswordResetToken(user_id=user_id, token_hash="reset-live", expires_at=now + timedelta(hours=1))
        )
        db.add(
            PasswordResetToken(user_id=user_id, token_hash="reset-old", expires_at=now - timedelta(hours=1))
        )
        db.add(
            EmailVerificationToken(user_id=user_id, token_hash="verify-old", expires_at=now - timedelta(days=2))
        )
        db.commit()

        removed = purge_expired_tokens(db)
        db.commit()

        assert removed == 4
        assert set(db.scalars(select(RefreshToken.token_hash)).all()) == {"live", "revoked-fresh"}
        assert db.scalars(select(PasswordResetToken.token_hash)).all() == ["reset-live"]
        assert count(db, EmailVerificationToken) == 0


def test_purge_is_idempotent_and_safe_on_empty_tables(db_session_factory):
    with db_session_factory() as db:
        assert purge_expired_tokens(db) == 0
        user_id = seed_user(db)
        add_refresh(db, user_id, "expired", -timedelta(days=1))
        db.commit()

        assert purge_expired_tokens(db) == 1
        db.commit()
        assert purge_expired_tokens(db) == 0


def test_rotated_session_still_detects_reuse_before_expiry(client, db_session_factory):
    """Уборка не должна превращать признак кражи в обычный 401."""
    payload = {"email": "user@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    tokens = client.post("/api/v1/auth/login", json=payload).json()

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()

    with db_session_factory() as db:
        purge_expired_tokens(db)
        db.commit()

    # старый токен отозван, но не истёк: он пережил уборку и по-прежнему гасит все сессии
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}).status_code == 401
