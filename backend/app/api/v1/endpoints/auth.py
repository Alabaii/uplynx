from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import OrgMember, User
from app.schemas import MeRead, Token, UserCreate, UserLogin, UserOrganizationRead, UserRead
from app.services.audit import record
from app.services.orgs import enforce_member_quota, ensure_membership, get_or_create_default_org

router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    if settings.deployment_mode == "team":
        user_count = db.scalar(select(func.count()).select_from(User)) or 0
        if user_count >= settings.team_max_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User limit reached: team deployment allows at most {settings.team_max_users} users",
            )
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=payload.email.lower(), hashed_password=hash_password(payload.password))
    db.add(user)
    db.flush()
    # регистрация создаёт членство в default-организации — её quota_members действует и здесь
    org = get_or_create_default_org(db)
    enforce_member_quota(db, org)
    ensure_membership(db, user, org)
    record(db, org_id=org.id, user_id=user.id, action="auth.register", entity="user", entity_id=str(user.id), payload={})
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # активная организация = единственное/первое членство
    org_id = db.scalar(
        select(OrgMember.org_id).where(OrgMember.user_id == user.id).order_by(OrgMember.id).limit(1)
    )
    extra_claims = {"org_id": org_id} if org_id is not None else None
    return Token(access_token=create_access_token(str(user.id), extra_claims=extra_claims))


@router.get("/me", response_model=MeRead)
def me(ctx: OrgContext = Depends(get_current_org_member)) -> MeRead:
    return MeRead(
        id=ctx.user.id,
        email=ctx.user.email,
        organization=UserOrganizationRead(id=ctx.org.id, name=ctx.org.name, slug=ctx.org.slug, role=ctx.role),
    )
