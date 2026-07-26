from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, require_role
from app.core.database import get_db
from app.models import OrgSecret, User
from app.schemas import OrgSecretRead, OrgSecretUpsert
from app.services.audit import record
from app.services.secrets import upsert_org_secret

router = APIRouter()


def to_secret_read(secret: OrgSecret, created_by_email: str | None) -> OrgSecretRead:
    return OrgSecretRead(
        name=secret.name,
        created_at=secret.created_at,
        updated_at=secret.updated_at,
        created_by_email=created_by_email,
    )


@router.get("", response_model=list[OrgSecretRead])
def list_secrets(
    ctx: OrgContext = Depends(get_current_org_member), db: Session = Depends(get_db)
) -> list[OrgSecretRead]:
    """Только имена: значение не отдаётся никому, включая владельца."""
    rows = db.execute(
        select(OrgSecret, User.email)
        .outerjoin(User, User.id == OrgSecret.created_by)
        .where(OrgSecret.org_id == ctx.org.id)
        .order_by(OrgSecret.name)
    ).all()
    return [to_secret_read(secret, email) for secret, email in rows]


@router.put("/{name}", response_model=OrgSecretRead)
def put_secret(
    name: str,
    payload: OrgSecretUpsert,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> OrgSecretRead:
    if name != payload.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Secret name in path and body must match"
        )
    secret = upsert_org_secret(db, ctx.org.id, payload.name, payload.value, ctx.user.id)
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="secret.upsert",
        entity="secret",
        entity_id=payload.name,
        payload={"name": payload.name},  # значение в аудит не пишем
    )
    db.commit()
    db.refresh(secret)
    return to_secret_read(secret, ctx.user.email)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_secret(
    name: str,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    secret = db.scalar(select(OrgSecret).where(OrgSecret.org_id == ctx.org.id, OrgSecret.name == name))
    if secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="secret.delete",
        entity="secret",
        entity_id=name,
        payload={"name": name},
    )
    # сценарии, ссылающиеся на удалённый секрет, упадут на ближайшей проверке
    # с понятной ошибкой: молча подставить пустое значение опаснее — тест логина
    # «прошёл бы успешно» с пустым паролем
    db.delete(secret)
    db.commit()
