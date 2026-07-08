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
    access_token_expire_minutes: int = 60 * 24
    scheduler_poll_seconds: int = 5
    # максимум мониторов одной организации в батче шедулера (fair scheduling)
    scheduler_org_batch_limit: int = 200
    check_timeout_seconds: int = 30
    retention_days: int = 365
    browser_concurrency: int = 2
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


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
