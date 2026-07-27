import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRETS = {"change-me-in-production", "change-me-change-me"}
# учётные данные из docker-compose.yml: они удобны для dev и известны всем, кто
# видел репозиторий. RLS и роль monitor_app защищают именно от того, кто добрался
# до сети контейнеров, — с дефолтным паролем эта защита обнуляется
DEFAULT_DATABASE_PASSWORDS = {"monitor", "monitor_app", "postgres"}
DEFAULT_BROKER_PASSWORDS = {"guest"}


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
    # предел на browser-сценарий ЦЕЛИКОМ: check_timeout_seconds ограничивает
    # отдельный шаг, поэтому длинный сценарий (или шаги, каждый из которых почти
    # укладывается в свой таймаут) держал бы воркер сколько угодно долго
    browser_scenario_timeout_seconds: int = Field(default=120, ge=10)
    # то же для HTTP-проверки. check_timeout_seconds уходит в httpx, а там таймаут
    # применяется к КАЖДОЙ операции (connect/read/write) по отдельности, а не к
    # запросу целиком: цель, отдающая по байту раз в 29 секунд, держит соединение
    # сколько угодно долго, и каждый хоп цепочки редиректов получает свой полный
    # таймаут заново. Без общего потолка десяток таких мониторов занимает все
    # http_concurrency слотов и останавливает HTTP-проверки всей платформы
    http_check_budget_seconds: int = Field(default=90, ge=10)
    # Sentry: пустой DSN — отключён (dev/self-hosted работают без него)
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0
    # порт /metrics для scheduler/воркеров; 0 — не поднимать (API отдаёт /metrics роутом)
    metrics_port: int = 0
    retention_days: int = 365
    # сколько проверок воркер выполняет одновременно (prefetch очереди). Проверка
    # почти всё время ждёт сеть, поэтому потолок здесь — не CPU, а число мониторов,
    # которые не должны ждать друг друга: при 1 недоступный адрес занимал воркер
    # на весь check_timeout_seconds и останавливал проверки всех организаций
    http_concurrency: int = Field(default=10, ge=1)
    # браузерных проверок одновременно — каждая держит свой Chromium (память!)
    browser_concurrency: int = Field(default=2, ge=1)
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
    # сколько организаций пользователь может создать сам (enterprise). Регистрация
    # уже даёт ему персональный воркспейс, а лимиты тарифа считаются НА организацию:
    # без потолка любой клиент обходил бы платный план, множа бесплатные воркспейсы
    max_owned_orgs_per_user: int = Field(default=3, ge=1)
    # сколько ДОВЕРЕННЫХ прокси стоит перед nginx приложения (он дописывает свой
    # адрес в X-Forwarded-For сам). 0 — nginx смотрит в интернет напрямую;
    # 1 — перед ним TLS-терминатор (Caddy из DEPLOY.md). Значение больше реального
    # означало бы доверие к подделанной клиентом части заголовка, поэтому
    # безопасный дефолт — 0 (см. client_ip в endpoints/auth.py).
    trusted_proxy_hops: int = Field(default=0, ge=0)
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    # второй лимит входа — на один адрес независимо от адресата: ключ ip+email
    # ограничивает подбор пароля к КОНКРЕТНОМУ аккаунту, но не перебор одного
    # пароля по списку email (password spraying), где каждая попытка идёт в свой
    # ключ. Потолок щедрый: успешный вход сбрасывает счётчик, поэтому офис за
    # общим NAT его не достигает, а скриптовый перебор — сразу
    login_ip_rate_limit_attempts: int = 20
    login_ip_rate_limit_window_seconds: int = 300
    register_rate_limit_attempts: int = 10
    register_rate_limit_window_seconds: int = 300
    forgot_rate_limit_attempts: int = 5
    forgot_rate_limit_window_seconds: int = 300
    # требовать подтверждение email перед входом; действует только если задан SMTP
    # (иначе письмо не отправить) — на dev/self-hosted без почты вход не блокируется
    require_email_verification: bool = True
    verify_rate_limit_attempts: int = 5
    verify_rate_limit_window_seconds: int = 300
    # rate-limit мутирующих запросов (POST/PUT/PATCH/DELETE вне /auth):
    # щедрый потолок против скриптового злоупотребления, обычный UI его не достигает
    mutation_rate_limit_attempts: int = 60
    mutation_rate_limit_window_seconds: int = 60
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


def validate_secret_encryption_key(settings: Settings) -> None:
    """SECRET_ENCRYPTION_KEY обязателен в production и не должен зависеть от JWT-секрета.

    Без него ключ шифрования деривируется из JWT_SECRET_KEY (см. core/security.py).
    Тогда ротация JWT-секрета — например, после его утечки — необратимо ломает
    расшифровку токенов Telegram и секретов воркспейсов: данные остаются в БД,
    но прочитать их уже нечем. Разделяем ключи, пока это ещё ничего не стоит.
    """
    from cryptography.fernet import Fernet

    if not settings.secret_encryption_key:
        message = (
            "SECRET_ENCRYPTION_KEY is not set: the encryption key is derived from JWT_SECRET_KEY, "
            "so rotating the JWT secret would make stored secrets unreadable. Generate one with "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
        if settings.environment == "production":
            raise RuntimeError(message)
        logging.getLogger(__name__).warning(message)
        return
    try:
        Fernet(settings.secret_encryption_key.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — падаем на старте, а не на первой расшифровке
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY is not a valid Fernet key (expected 32 url-safe base64-encoded bytes)"
        ) from exc

def validate_cors_origins(settings: Settings) -> None:
    """В production запрещаем '*': вместе с allow_credentials это снимает CORS совсем.

    Starlette при allow_origins=['*'] и allow_credentials=True отражает Origin
    запроса обратно, то есть любой сайт сможет ходить в API с куками и заголовками
    пользователя. Опечатка в .env не должна стоить так дорого.
    """
    origins = settings.cors_origins_list
    logger = logging.getLogger(__name__)
    if "*" in origins:
        message = "CORS_ORIGINS contains '*' while credentials are allowed; list the frontend origins explicitly"
        if settings.environment == "production":
            raise RuntimeError(message)
        logger.warning(message)
        return
    malformed = [origin for origin in origins if not origin.startswith(("http://", "https://"))]
    if malformed:
        # частая ошибка: домен без схемы — браузер такой origin не сопоставит,
        # и запросы фронтенда молча начнут блокироваться
        raise RuntimeError(f"CORS_ORIGINS entries must include a scheme: {', '.join(malformed)}")


def validate_infrastructure_credentials(settings: Settings) -> None:
    """В production запрещаем дефолтные пароли БД и брокера.

    JWT-секрет и ключ шифрования уже проверяются при старте, а пароли postgres
    и rabbitmq из docker-compose (monitor / monitor_app / guest) — нет: забытый
    .env оставлял бы инфраструктуру на паролях, известных каждому, кто видел
    репозиторий. Порты в прод-оверлее закрыты, но именно от доступа в сеть
    контейнеров и защищают RLS с непривилегированной ролью.
    """
    from urllib.parse import urlsplit

    logger = logging.getLogger(__name__)
    problems: list[str] = []
    for name, url, defaults in (
        ("DATABASE_URL", settings.database_url, DEFAULT_DATABASE_PASSWORDS),
        ("RABBITMQ_URL", settings.rabbitmq_url, DEFAULT_BROKER_PASSWORDS),
    ):
        try:
            password = urlsplit(url).password
        except ValueError:  # некорректный URL — не наша забота, упадёт при подключении
            continue
        if password and password in defaults:
            # сам пароль не печатаем: сообщение уходит в логи и Sentry, а имени
            # переменной достаточно, чтобы понять, что править
            problems.append(f"{name} uses the well-known default password from the repository")
    if not problems:
        return
    message = "; ".join(problems) + "; set your own credentials in .env"
    if settings.environment == "production":
        raise RuntimeError(message)
    logger.warning(message)


@lru_cache
def get_settings() -> Settings:
    return Settings()
