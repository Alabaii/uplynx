import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, get_current_user, require_role
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_token
from app.models import AuditLog, Organization, OrgMember, RefreshToken, User
from app.schemas import (
    AuditLogRead,
    OrgCreate,
    OrgMemberAdd,
    OrgMemberRead,
    OrgMemberUpdate,
    OrgRead,
    OrgUpdate,
    SwitchOrgRequest,
    Token,
)
from app.services.audit import record
from app.services.email import send_email
from app.services.orgs import enforce_member_quota

logger = logging.getLogger(__name__)

router = APIRouter()


def to_org_read(org: Organization, role: str) -> OrgRead:
    return OrgRead(
        id=org.id,
        name=org.name,
        slug=org.slug,
        role=role,
        quota_monitors=org.quota_monitors,
        quota_members=org.quota_members,
        status_page_enabled=org.status_page_enabled,
        alert_emails=org.alert_emails or [],
    )


@router.get("", response_model=list[OrgRead])
def list_my_orgs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[OrgRead]:
    rows = db.execute(
        select(Organization, OrgMember.role)
        .join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user.id)
        .order_by(OrgMember.id)
    ).all()
    return [to_org_read(org, role) for org, role in rows]


@router.post("", response_model=OrgRead, status_code=status.HTTP_201_CREATED)
def create_org(
    payload: OrgCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgRead:
    if get_settings().deployment_mode == "team":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Creating organizations requires the enterprise deployment mode",
        )
    if db.scalar(select(Organization).where(Organization.slug == payload.slug)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization slug already exists")
    org = Organization(name=payload.name, slug=payload.slug)
    db.add(org)
    db.flush()
    db.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
    record(
        db,
        org_id=org.id,
        user_id=user.id,
        action="org.create",
        entity="org",
        entity_id=org.slug,
        payload={"name": org.name},
    )
    db.commit()
    db.refresh(org)
    return to_org_read(org, "owner")


@router.patch("/current", response_model=OrgRead)
def update_current_org(
    payload: OrgUpdate,
    ctx: OrgContext = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> OrgRead:
    data = payload.model_dump(exclude_unset=True)
    for field in ("name", "status_page_enabled", "alert_emails"):
        if data.get(field) is None:
            data.pop(field, None)  # NOT NULL-поля, явный null игнорируем
    for field, value in data.items():
        setattr(ctx.org, field, value)
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="org.update",
        entity="org",
        entity_id=ctx.org.slug,
        payload={"changes": sorted(data)},
    )
    db.commit()
    db.refresh(ctx.org)
    return to_org_read(ctx.org, ctx.role)


@router.post("/{org_id}/switch", response_model=Token)
def switch_org(
    org_id: int,
    payload: SwitchOrgRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Token:
    member = db.scalar(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user.id))
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")
    if payload and payload.refresh_token:
        # переключаем активную организацию refresh-сессии: после истечения access
        # refresh выдаст токен с той же организацией, а не вернёт пользователя в первую
        session = db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(payload.refresh_token),
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        if session is not None:
            session.org_id = org_id
            db.commit()
    return Token(access_token=create_access_token(str(user.id), extra_claims={"org_id": org_id}))


@router.get("/current/members", response_model=list[OrgMemberRead])
def list_members(
    ctx: OrgContext = Depends(get_current_org_member), db: Session = Depends(get_db)
) -> list[OrgMemberRead]:
    rows = db.execute(
        select(OrgMember, User.email)
        .join(User, User.id == OrgMember.user_id)
        .where(OrgMember.org_id == ctx.org.id)
        .order_by(OrgMember.id)
    ).all()
    return [
        OrgMemberRead(user_id=member.user_id, email=email, role=member.role, created_at=member.created_at)
        for member, email in rows
    ]


@router.post("/current/members", response_model=OrgMemberRead, status_code=status.HTTP_201_CREATED)
def add_member(
    payload: OrgMemberAdd,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> OrgMemberRead:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No registered user with this email")
    existing = db.scalar(select(OrgMember).where(OrgMember.org_id == ctx.org.id, OrgMember.user_id == user.id))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")
    enforce_member_quota(db, ctx.org)
    member = OrgMember(org_id=ctx.org.id, user_id=user.id, role=payload.role)
    db.add(member)
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="member.add",
        entity="member",
        entity_id=str(user.id),
        payload={"member_email": user.email, "role": payload.role},
    )
    db.commit()
    db.refresh(member)
    try:
        # уведомление — best effort: сбой почты не ломает добавление участника
        send_email(
            user.email,
            f"You were added to {ctx.org.name} on PWA Monitor",
            f"You were added to the '{ctx.org.name}' organization on PWA Monitor "
            f"with the {member.role} role.\n\n"
            f"Open the dashboard: {get_settings().app_base_url}\n",
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send member-added email to %s", user.email)
    return OrgMemberRead(user_id=member.user_id, email=user.email, role=member.role, created_at=member.created_at)


@router.patch("/current/members/{user_id}", response_model=OrgMemberRead)
def update_member_role(
    user_id: int,
    payload: OrgMemberUpdate,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> OrgMemberRead:
    member = db.scalar(select(OrgMember).where(OrgMember.org_id == ctx.org.id, OrgMember.user_id == user_id))
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.role == "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change the owner's role")
    member.role = payload.role
    email = db.scalar(select(User.email).where(User.id == member.user_id))
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="member.role_change",
        entity="member",
        entity_id=str(member.user_id),
        payload={"member_email": email, "role": payload.role},
    )
    db.commit()
    db.refresh(member)
    return OrgMemberRead(user_id=member.user_id, email=email, role=member.role, created_at=member.created_at)


@router.delete("/current/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: int,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    member = db.scalar(select(OrgMember).where(OrgMember.org_id == ctx.org.id, OrgMember.user_id == user_id))
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.role == "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot remove the organization owner")
    if member.user_id == ctx.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself")
    email = db.scalar(select(User.email).where(User.id == member.user_id))
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="member.remove",
        entity="member",
        entity_id=str(member.user_id),
        payload={"member_email": email},
    )
    db.delete(member)
    db.commit()


@router.get("/current/audit", response_model=list[AuditLogRead])
def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[AuditLogRead]:
    rows = db.execute(
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.org_id == ctx.org.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        AuditLogRead(
            id=entry.id,
            action=entry.action,
            entity=entry.entity,
            entity_id=entry.entity_id,
            payload=entry.payload or {},
            created_at=entry.created_at,
            actor_email=email,
        )
        for entry, email in rows
    ]
