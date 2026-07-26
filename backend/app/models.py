from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # момент подтверждения email; NULL — не подтверждён
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    monitors: Mapped[list["Monitor"]] = relationship(back_populates="user")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    quota_monitors: Mapped[int | None] = mapped_column(Integer)
    quota_members: Mapped[int | None] = mapped_column(Integer)
    status_page_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_emails: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    plan_slug: Mapped[str] = mapped_column(
        ForeignKey("plans.slug"), nullable=False, default="free", server_default="free"
    )


class Plan(Base):
    """Тарифный план платформы. Редактируется суперадмином в админ-панели.

    Глобальная таблица (не org-scoped, без RLS). Лимиты пока информационные —
    их принудительное применение (гейтинг) выполняется отдельным этапом.
    max_members NULL — без лимита участников.
    """

    __tablename__ = "plans"

    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # цена в копейках (рублёвый биллинг: ЮKassa/Robokassa, решение 2026-07-10)
    price_monthly_kopeks: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_discount_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_monitors: Mapped[int] = mapped_column(Integer, nullable=False)
    min_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_browser_monitors: Mapped[int] = mapped_column(Integer, nullable=False)
    browser_min_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    max_members: Mapped[int | None] = mapped_column(Integer)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # в БД хранится только sha256-hex токена — утечка таблицы не даёт сбросить пароль
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RefreshToken(Base):
    """Сессия пользователя: длинный refresh-токен с ротацией.

    В БД только sha256-hex. revoked_at ставится при ротации/логауте/сбросе пароля;
    предъявление отозванного токена — признак кражи, гасит все сессии пользователя.
    org_id — активная организация сессии (переносится в org_id claim access-токена).
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        Index("ix_email_verification_tokens_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # как и в password_reset: в БД только sha256-hex, утечка таблицы бесполезна
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_monitor_user_slug"),
        Index("ix_monitors_user_id", "user_id"),
        Index("ix_monitors_org_id", "org_id"),
        Index("ix_monitors_next_run_at", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="paused", nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048))
    interval: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # срок действия TLS-сертификата (обновляется воркером на каждой https-проверке)
    ssl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # самый острый порог (в днях), по которому уже отправлен ssl-алерт; NULL — не алертили
    ssl_alerted_days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="monitors")
    results: Mapped[list["CheckResult"]] = relationship(back_populates="monitor")


class SchedulerHeartbeat(Base):
    """Единственная строка (id=1): момент последнего тика шедулера.

    Позволяет внешнему liveness-пробу заметить, что шедулер перестал публиковать
    проверки. Не org-scoped — состояние процесса, а не данные арендатора.
    """

    __tablename__ = "scheduler_heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_check_results_task_id"),
        Index("ix_check_results_monitor_timestamp", "monitor_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    monitor: Mapped[Monitor] = relationship(back_populates="results")


class UptimeDaily(Base):
    __tablename__ = "uptime_daily"
    __table_args__ = (
        UniqueConstraint("monitor_id", "date", name="uq_uptime_daily_monitor_date"),
        Index("ix_uptime_daily_org_id", "org_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    checks_total: Mapped[int] = mapped_column(Integer, nullable=False)
    checks_up: Mapped[int] = mapped_column(Integer, nullable=False)
    checks_degraded: Mapped[int] = mapped_column(Integer, nullable=False)
    checks_down: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_response_ms: Mapped[int | None] = mapped_column(Integer)


class ConfigVersion(Base):
    __tablename__ = "config_versions"
    __table_args__ = (
        Index("ix_config_versions_user_version", "user_id", "version"),
        Index("ix_config_versions_org_id", "org_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
        Index("ix_push_subscriptions_org_id", "org_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_org_created", "org_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # nullable — на будущее для системных событий (scheduler, воркеры)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_org_id", "org_id"),
        Index("ix_incidents_monitor_id", "monitor_id"),
        Index("ix_incidents_started_at", "started_at"),
        Index("ix_incidents_org_started", "org_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # open | resolved
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # down | degraded — худшее наблюдённое
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    trigger_error: Mapped[str | None] = mapped_column(Text)
    # момент последнего повторного алерта; NULL — уведомляли только при открытии
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    __table_args__ = (
        Index("ix_maintenance_windows_org_id", "org_id"),
        Index("ix_maintenance_windows_org_ends", "org_id", "ends_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # null — окно на всю организацию
    monitor_id: Mapped[int | None] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OrgSecret(Base):
    """Секрет воркспейса для browser-сценариев: подстановка ${NAME} в шаги.

    Раньше ${NAME} резолвился из окружения воркера — в SaaS это давало любому
    арендатору ключи платформы (JWT_SECRET_KEY, DATABASE_URL) и секреты соседей.
    Теперь значения принадлежат организации, шифруются тем же Fernet-ключом,
    что и токен Telegram, и наружу (в API и в тексты ошибок) не отдаются.
    """

    __tablename__ = "org_secrets"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_secret_name"),
        Index("ix_org_secrets_org_id", "org_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # имя плейсхолдера без ${}: ловится ENV_PLACEHOLDER_RE в services/checks.py
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    value_secret: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TelegramIntegration(Base):
    __tablename__ = "telegram_integrations"
    __table_args__ = (
        Index("ix_telegram_integrations_org_id", "org_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    bot_token_secret: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[str] = mapped_column(String(120), nullable=False)
    alert_scopes: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
