import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    if settings.secret_encryption_key:
        key = settings.secret_encryption_key.encode("utf-8")
    else:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def hash_token(token: str) -> str:
    """sha256-hex одноразового токена (refresh/reset/verify) — в БД сырой токен не хранится."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _password_bytes(password: str) -> bytes:
    # bcrypt учитывает максимум 72 байта; passlib (использовался раньше) усекал
    # молча, bcrypt>=5 бросает ValueError — сохраняем прежнюю семантику явно
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Совместимо со старыми passlib-хэшами: формат $2b$ одинаковый."""
    try:
        return bcrypt.checkpw(_password_bytes(password), hashed_password.encode("utf-8"))
    except ValueError:
        # повреждённый/чужой формат хэша — просто отказ, не 500
        return False


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire, **(extra_claims or {})}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token_payload(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def decode_access_token(token: str) -> str | None:
    payload = decode_token_payload(token)
    if not payload:
        return None
    subject = payload.get("sub")
    return str(subject) if subject else None
