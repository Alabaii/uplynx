from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, get_current_user, require_role
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import Organization, OrgMember, User
from app.schemas import OrgCreate, OrgMemberAdd, OrgMemberRead, OrgMemberUpdate, OrgRead, OrgUpdate, Token
from app.services.orgs import enforce_member_quota

router = APIRouter()


def to_org_read(org: Organization, role: str) -> OrgRead:
    return OrgRead(
        id=org.id,
        name=org.name,
        slug=org.slug,
        role=role,
        quota_monitors=org.quota_monitors,
        quota_members=org.quota_members,
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
    if data.get("name") is None:
        data.pop("name", None)  # name — NOT NULL, явный null игнорируем
    for field, value in data.items():
        setattr(ctx.org, field, value)
    db.commit()
    db.refresh(ctx.org)
    return to_org_read(ctx.org, ctx.role)


@router.post("/{org_id}/switch", response_model=Token)
def switch_org(
    org_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Token:
    member = db.scalar(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user.id))
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")
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
    db.commit()
    db.refresh(member)
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
    db.commit()
    db.refresh(member)
    email = db.scalar(select(User.email).where(User.id == member.user_id))
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
    db.delete(member)
    db.commit()
