import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRETS = {"change-me-in-production", "change-me-change-me"}


class Settings(BaseSettings):
    app_name: str = "PWA Monitor Backend"
    environment: Literal["development", "local", "test", "production"] = "development"
    database_url: str = "sqlite:///./monitor.db"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    jwt_secret_key: str = Field(default="change-me-in-production", min_length=16)
    jwt_algorithm: str = "HS256"
    # короткий access + refresh с ротацией: отзыв сессии срабатывает максимум за 15 минут
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    scheduler_poll_seconds: int = 5
    # максимум мониторов одной организации в батче шедулера (fair scheduling)
    scheduler_org_batch_limit: int = 200
    # heartbeat шедулера старше этого — /health/scheduler отдаёт 503 (liveness)
    scheduler_heartbeat_stale_seconds: int = 30
    check_timeout_seconds: int = 30
    # Sentry: пустой DSN — отключён (dev/self-hosted работают без него)
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0
    # порт /metrics для scheduler/воркеров; 0 — не поднимать (API отдаёт /metrics роутом)
    metrics_port: int = 0
    retention_days: int = 365
    browser_concurrency: int = 2
    # SSRF-защита: по умолчанию мониторы не могут вести во внутреннюю сеть.
    # on-prem-инсталляции ставят true, чтобы мониторить внутренние сервисы.
    allow_private_targets: bool = False
    telegram_api_base: str = "https://api.telegram.org"
    # VAPID-ключи для web push (python -m app.tools.vapid); если не заданы — push отключён
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@example.com"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    secret_encryption_key: str | None = None
    deployment_mode: Literal["team", "enterprise"] = "team"
    team_max_users: int = 20
    team_max_monitors: int = 100
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    register_rate_limit_attempts: int = 10
    register_rate_limit_window_seconds: int = 300
    forgot_rate_limit_attempts: int = 5
    forgot_rate_limit_window_seconds: int = 300
    # требовать подтверждение email перед входом; действует только если задан SMTP
    # (иначе письмо не отправить) — на dev/self-hosted без почты вход не блокируется
    require_email_verification: bool = True
    verify_rate_limit_attempts: int = 5
    verify_rate_limit_window_seconds: int = 300
    # SMTP для писем (сброс пароля, email-алерты); если host не задан — email отключён
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "PWA Monitor <no-reply@localhost>"
    smtp_starttls: bool = True
    # базовый URL приложения для ссылок в письмах
    app_base_url: str = "http://localhost:5173"
    # платформенные суперадмины (админ-панель /admin): email через запятую;
    # пусто — админ-панель недоступна никому
    superuser_emails: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def superuser_emails_list(self) -> list[str]:
        return [email.strip().lower() for email in self.superuser_emails.split(",") if email.strip()]


def validate_jwt_secret(settings: Settings) -> None:
    if settings.jwt_secret_key not in DEFAULT_JWT_SECRETS:
        return
    message = "JWT_SECRET_KEY is set to a well-known default value; set a strong unique secret"
    if settings.environment == "production":
        raise RuntimeError(message)
    logging.getLogger(__name__).warning(message)


@lru_cache
def get_settings() -> Settings:
    return Settings()
