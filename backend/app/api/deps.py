from typing import Callable, NamedTuple

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token, decode_token_payload
from app.models import Organization, OrgMember, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ROLE_ORDER = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


class OrgContext(NamedTuple):
    user: User
    org: Organization
    role: str


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    subject = decode_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    user = db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return user


def is_superuser(user: User) -> bool:
    """Платформенный суперадмин — по списку email в настройках (SUPERUSER_EMAILS)."""
    return user.email.lower() in get_settings().superuser_emails_list


def require_superuser(user: User = Depends(get_current_user)) -> User:
    """Доступ к /admin: кросс-организационные запросы, RLS-контекст НЕ выставляется.

    Политики org_isolation (0008) дают полный доступ, когда app.org_id не задан, —
    для платформенной админки это осознанно.
    """
    if not is_superuser(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires platform admin access")
    return user


def get_current_org_member(
    token: str = Depends(oauth2_scheme),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    payload = decode_token_payload(token) or {}
    token_org_id = payload.get("org_id")

    query = (
        select(Organization, OrgMember.role)
        .join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user.id)
    )
    if token_org_id is not None:
        # активная организация из токена — с проверкой членства
        query = query.where(Organization.id == token_org_id)
    else:
        # старый токен без org_id — первое членство (обратная совместимость)
        query = query.order_by(OrgMember.id)
    row = db.execute(query.limit(1)).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organization membership")
    org, role = row
    bind_org_to_rls(db, org.id)
    return OrgContext(user=user, org=org, role=role)


def bind_org_to_rls(db: Session, org_id: int) -> None:
    """Привязывает сессию к организации для RLS-политик (миграция 0008).

    third=true — SET LOCAL: настройка действует до конца транзакции и не утекает
    в чужие запросы через пул соединений. Но и сбрасывается она вместе с
    транзакцией: эндпоинт, который коммитит в середине работы (создание монитора
    сохраняет снимок конфига и коммитит, а потом читает монитор заново), остаток
    запроса выполнял уже без контекста — а политики при незаданном app.org_id
    пропускают всё. Поэтому настройка ставится не один раз, а на начало КАЖДОЙ
    транзакции этой сессии.

    На sqlite (юнит-тесты, self-hosted без PostgreSQL) — no-op: там нет ни
    set_config, ни самих политик.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    statement = text("SELECT set_config('app.org_id', :v, true)")
    params = {"v": str(org_id)}

    @event.listens_for(db, "after_begin")
    def _apply_on_every_transaction(_session, _transaction, connection) -> None:  # type: ignore[no-untyped-def]
        connection.execute(statement, params)

    # текущая транзакция уже открыта (аутентификация читала пользователя) —
    # её событие after_begin уже прошло, выставляем настройку напрямую
    db.execute(statement, params)


def require_role(minimum: str) -> Callable[..., OrgContext]:
    minimum_rank = ROLE_ORDER[minimum]

    def dependency(ctx: OrgContext = Depends(get_current_org_member)) -> OrgContext:
        if ROLE_ORDER.get(ctx.role, -1) < minimum_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{minimum}' or higher",
            )
        return ctx

    return dependency
