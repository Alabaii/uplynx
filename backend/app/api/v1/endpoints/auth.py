from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member
from app.core.config import get_settings
from app.core.database import get_db
from app.core.ratelimit import get_login_limiter, get_register_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models import OrgMember, User
from app.schemas import MeRead, Token, UserCreate, UserLogin, UserOrganizationRead, UserRead
from app.services.audit import record
from app.services.orgs import enforce_member_quota, ensure_membership, get_or_create_default_org

router = APIRouter()


def client_ip(request: Request) -> str:
    # за nginx-прокси реальный адрес приходит в X-Forwarded-For; прямой доступ
    # к бэкенду в проде закрыт (порт не публикуется), так что заголовку можно верить
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(limiter, key: str) -> None:
    retry_after = limiter.hit(key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts, try again later",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> User:
    enforce_rate_limit(get_register_limiter(), f"register:{client_ip(request)}")
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
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)) -> Token:
    limiter = get_login_limiter()
    limiter_key = f"login:{client_ip(request)}:{payload.email.lower()}"
    enforce_rate_limit(limiter, limiter_key)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # успешный вход сбрасывает счётчик неудачных попыток
    limiter.reset(limiter_key)
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
        organization=UserOrganizationRead(
            id=ctx.org.id,
            name=ctx.org.name,
            slug=ctx.org.slug,
            role=ctx.role,
            status_page_enabled=ctx.org.status_page_enabled,
        ),
    )
