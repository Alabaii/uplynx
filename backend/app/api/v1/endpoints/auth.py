import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member
from app.core.config import get_settings
from app.core.database import get_db
from app.core.ratelimit import (
    get_forgot_password_limiter,
    get_login_limiter,
    get_register_limiter,
    get_verify_email_limiter,
)
from app.core.security import create_access_token, hash_password, hash_token, verify_password
from app.models import EmailVerificationToken, OrgMember, PasswordResetToken, RefreshToken, User
from app.schemas import (
    ForgotPasswordRequest,
    LogoutRequest,
    MeRead,
    RefreshRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserLogin,
    UserOrganizationRead,
    UserRead,
    VerifyEmailRequest,
)
from app.services.audit import record
from app.services.email import email_enabled, send_email
from app.services.orgs import enforce_member_quota, ensure_membership, get_or_create_default_org

router = APIRouter()

RESET_TOKEN_TTL = timedelta(hours=1)
VERIFY_TOKEN_TTL = timedelta(hours=24)


def verification_required() -> bool:
    """Гейт активен только если можем отправить письмо — иначе вход не заблокировать."""
    return get_settings().require_email_verification and email_enabled()


def issue_verification_token(db: Session, user: User) -> str:
    """Создаёт токен верификации в сессии (без commit) и гасит прежние неиспользованные."""
    now = datetime.now(timezone.utc)
    db.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))
        .values(used_at=now)
    )
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=now + VERIFY_TOKEN_TTL,
        )
    )
    return token


def send_verification_email(email: str, token: str) -> None:
    link = f"{get_settings().app_base_url}/verify-email?token={token}"
    send_email(
        email,
        "Verify your PWA Monitor email",
        "Confirm your email address to activate your PWA Monitor account:\n\n"
        f"{link}\n\n"
        "The link expires in 24 hours. If you did not create an account, ignore this email.\n",
    )


def issue_refresh_token(db: Session, user: User, org_id: int | None) -> str:
    """Создаёт refresh-сессию в db-сессии (без commit); возвращает сырой токен."""
    token = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(token),
            org_id=org_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_expire_days),
        )
    )
    return token


def revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


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
    verify_token = issue_verification_token(db, user) if verification_required() else None
    db.commit()
    db.refresh(user)
    if verify_token:
        # письмо — после commit, чтобы токен уже был в БД
        send_verification_email(user.email, verify_token)
    return user


@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)) -> Token:
    limiter = get_login_limiter()
    limiter_key = f"login:{client_ip(request)}:{payload.email.lower()}"
    enforce_rate_limit(limiter, limiter_key)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if verification_required() and user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox for the verification link.",
        )
    # успешный вход сбрасывает счётчик неудачных попыток
    limiter.reset(limiter_key)
    # активная организация = единственное/первое членство
    org_id = db.scalar(
        select(OrgMember.org_id).where(OrgMember.user_id == user.id).order_by(OrgMember.id).limit(1)
    )
    extra_claims = {"org_id": org_id} if org_id is not None else None
    refresh_token = issue_refresh_token(db, user, org_id)
    db.commit()
    return Token(
        access_token=create_access_token(str(user.id), extra_claims=extra_claims),
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> Token:
    """Скользящая ротация: старый refresh гасится, выдаётся новая пара access+refresh."""
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    session = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(payload.refresh_token)))
    if session is None:
        raise invalid
    now = datetime.now(timezone.utc)
    if session.revoked_at is not None:
        # повторное предъявление отозванного токена — признак кражи: гасим все сессии пользователя
        revoke_all_refresh_tokens(db, session.user_id)
        db.commit()
        raise invalid
    expires_at = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise invalid
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise invalid
    # членство могло измениться с момента логина — org сессии проверяется заново
    org_id = session.org_id
    if org_id is not None and not db.scalar(
        select(OrgMember.id).where(OrgMember.org_id == org_id, OrgMember.user_id == user.id)
    ):
        org_id = None
    if org_id is None:
        org_id = db.scalar(
            select(OrgMember.org_id).where(OrgMember.user_id == user.id).order_by(OrgMember.id).limit(1)
        )
    session.revoked_at = now
    new_refresh = issue_refresh_token(db, user, org_id)
    db.commit()
    extra_claims = {"org_id": org_id} if org_id is not None else None
    return Token(
        access_token=create_access_token(str(user.id), extra_claims=extra_claims),
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> None:
    # всегда 204: логаут идемпотентен, существование токена не раскрывается
    session = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(payload.refresh_token)))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> None:
    # всегда 204 — существование аккаунта не раскрывается
    enforce_rate_limit(get_forgot_password_limiter(), f"forgot:{client_ip(request)}")
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user:
        return
    now = datetime.now(timezone.utc)
    # одновременно активен один токен — старые неиспользованные гасим
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=now + RESET_TOKEN_TTL,
        )
    )
    db.commit()
    reset_link = f"{get_settings().app_base_url}/reset-password?token={token}"
    send_email(
        user.email,
        "Reset your PWA Monitor password",
        "Use the link below to reset your PWA Monitor password:\n\n"
        f"{reset_link}\n\n"
        "The link expires in 1 hour. If you did not request a reset, ignore this email.\n",
    )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> None:
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    invalid = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    if not reset or reset.used_at is not None:
        raise invalid
    # sqlite отдаёт naive datetime — нормализуем к UTC перед сравнением
    expires_at = reset.expires_at if reset.expires_at.tzinfo else reset.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise invalid
    user = db.get(User, reset.user_id)
    if not user:
        raise invalid
    user.hashed_password = hash_password(payload.new_password)
    reset.used_at = datetime.now(timezone.utc)
    # смена пароля убивает все сессии: украденный refresh-токен перестаёт работать
    revoke_all_refresh_tokens(db, user.id)
    org_id = db.scalar(
        select(OrgMember.org_id).where(OrgMember.user_id == user.id).order_by(OrgMember.id).limit(1)
    )
    if org_id is not None:
        record(
            db,
            org_id=org_id,
            user_id=user.id,
            action="auth.password_reset",
            entity="user",
            entity_id=str(user.id),
            payload={},
        )
    db.commit()


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> None:
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    token = db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash))
    invalid = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    if not token or token.used_at is not None:
        raise invalid
    expires_at = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise invalid
    user = db.get(User, token.user_id)
    if not user:
        raise invalid
    now = datetime.now(timezone.utc)
    if user.email_verified_at is None:
        user.email_verified_at = now
    token.used_at = now
    db.commit()


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
def resend_verification(
    payload: ResendVerificationRequest, request: Request, db: Session = Depends(get_db)
) -> None:
    # всегда 204 — существование аккаунта и статус верификации не раскрываются
    enforce_rate_limit(get_verify_email_limiter(), f"verify:{client_ip(request)}")
    if not verification_required():
        return
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or user.email_verified_at is not None:
        return
    token = issue_verification_token(db, user)
    db.commit()
    send_verification_email(user.email, token)


@router.get("/me", response_model=MeRead)
def me(ctx: OrgContext = Depends(get_current_org_member)) -> MeRead:
    # verified=True, когда подтверждение не требуется — фронту нечего показывать
    email_verified = ctx.user.email_verified_at is not None or not verification_required()
    return MeRead(
        id=ctx.user.id,
        email=ctx.user.email,
        email_verified=email_verified,
        organization=UserOrganizationRead(
            id=ctx.org.id,
            name=ctx.org.name,
            slug=ctx.org.slug,
            role=ctx.role,
            status_page_enabled=ctx.org.status_page_enabled,
        ),
    )
