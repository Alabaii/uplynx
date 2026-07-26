"""Секреты воркспейса для browser-сценариев.

Значения хранятся зашифрованными (тот же Fernet-ключ, что и у токена Telegram)
и расшифровываются только в двух местах: здесь при подстановке в шаги воркером
и нигде больше. В API уходят одни имена — см. schemas.OrgSecretRead.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.models import OrgSecret


def load_org_secrets(db: Session, org_id: int) -> dict[str, str]:
    """{имя: значение} всех секретов организации; пустой словарь, если их нет."""
    rows = db.scalars(select(OrgSecret).where(OrgSecret.org_id == org_id)).all()
    return {row.name: decrypt_secret(row.value_secret) for row in rows}


def upsert_org_secret(db: Session, org_id: int, name: str, value: str, user_id: int) -> OrgSecret:
    """Создаёт секрет или заменяет значение существующего. Без commit."""
    secret = db.scalar(select(OrgSecret).where(OrgSecret.org_id == org_id, OrgSecret.name == name))
    if secret is None:
        secret = OrgSecret(org_id=org_id, name=name, value_secret=encrypt_secret(value), created_by=user_id)
        db.add(secret)
    else:
        secret.value_secret = encrypt_secret(value)
    return secret
