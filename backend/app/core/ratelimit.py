from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import RateLimitHit

# сколько держать строки брошенных ключей до суточной уборки шедулера
ABANDONED_KEY_TTL = timedelta(days=1)


class DatabaseRateLimiter:
    """Скользящее окно в БД: лимит общий для всех реплик API.

    В памяти процесса счётчики множились бы на число реплик, а словарь
    попыток рос бы без границ. Здесь просроченные строки ключа удаляются
    при следующей его попытке, брошенные ключи — уборкой шедулера.
    """

    def __init__(self, scope: str, max_attempts: int, window_seconds: float) -> None:
        self.scope = scope
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def _lock_window(self, db: Session, key: str) -> None:
        """Сериализует окно одного ключа между репликами до конца транзакции.

        Подсчёт попыток и запись новой обязаны быть неделимы: иначе параллельный
        залп читает один и тот же count до вставок и проходит целиком — пять
        разрешённых попыток входа превращаются в сколько угодно одновременных.
        Лок берётся на пару (scope, key), поэтому разные ключи не мешают друг другу.
        """
        if db.get_bind().dialect.name != "postgresql":
            # sqlite (тесты, self-hosted одиночный процесс) пишет с блокировкой всей БД
            return
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"{self.scope}:{key}"})

    def hit(self, key: str) -> float | None:
        """Регистрирует попытку. None — разрешено; иначе секунды до разблокировки.

        Синхронная: в async-коде вызывать через asyncio.to_thread — иначе три
        запроса к БД выполняются прямо в event loop.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.window_seconds)
        with SessionLocal() as db:
            self._lock_window(db, key)
            db.execute(
                delete(RateLimitHit).where(
                    RateLimitHit.scope == self.scope,
                    RateLimitHit.key == key,
                    RateLimitHit.hit_at < window_start,
                )
            )
            count, oldest = db.execute(
                select(func.count(RateLimitHit.id), func.min(RateLimitHit.hit_at)).where(
                    RateLimitHit.scope == self.scope, RateLimitHit.key == key
                )
            ).one()
            if count >= self.max_attempts and oldest is not None:
                db.commit()
                # sqlite отдаёт naive datetime, postgres — aware
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=timezone.utc)
                return max(self.window_seconds - (now - oldest).total_seconds(), 0.0)
            db.add(RateLimitHit(scope=self.scope, key=key, hit_at=now))
            db.commit()
            return None

    def reset(self, key: str) -> None:
        with SessionLocal() as db:
            db.execute(
                delete(RateLimitHit).where(RateLimitHit.scope == self.scope, RateLimitHit.key == key)
            )
            db.commit()


def purge_stale_rate_limits(db) -> int:  # type: ignore[no-untyped-def]
    """Убирает строки ключей, которые перестали обращаться (их некому вычистить)."""
    cutoff = datetime.now(timezone.utc) - ABANDONED_KEY_TTL
    return db.execute(delete(RateLimitHit).where(RateLimitHit.hit_at < cutoff)).rowcount


@lru_cache
def get_login_limiter() -> DatabaseRateLimiter:
    settings = get_settings()
    return DatabaseRateLimiter(
        "login", settings.login_rate_limit_attempts, settings.login_rate_limit_window_seconds
    )


@lru_cache
def get_register_limiter() -> DatabaseRateLimiter:
    settings = get_settings()
    return DatabaseRateLimiter(
        "register", settings.register_rate_limit_attempts, settings.register_rate_limit_window_seconds
    )


@lru_cache
def get_forgot_password_limiter() -> DatabaseRateLimiter:
    settings = get_settings()
    return DatabaseRateLimiter(
        "forgot", settings.forgot_rate_limit_attempts, settings.forgot_rate_limit_window_seconds
    )


@lru_cache
def get_verify_email_limiter() -> DatabaseRateLimiter:
    settings = get_settings()
    return DatabaseRateLimiter(
        "verify", settings.verify_rate_limit_attempts, settings.verify_rate_limit_window_seconds
    )


@lru_cache
def get_mutation_limiter() -> DatabaseRateLimiter:
    settings = get_settings()
    return DatabaseRateLimiter(
        "mutation", settings.mutation_rate_limit_attempts, settings.mutation_rate_limit_window_seconds
    )
