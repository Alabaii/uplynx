from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    org_id: int,
    user_id: int | None,
    action: str,
    entity: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Добавляет запись аудита в сессию БЕЗ commit.

    Запись коммитится вместе с бизнес-транзакцией вызывающего кода — это гарантирует
    атомарность «действие + запись»: откат действия откатывает и аудит.
    payload — краткие детали, НИКАКИХ секретов.
    """
    entry = AuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        payload=payload or {},
    )
    db.add(entry)
    return entry
