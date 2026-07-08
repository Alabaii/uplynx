from typing import Callable, NamedTuple

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    return OrgContext(user=user, org=org, role=role)


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
