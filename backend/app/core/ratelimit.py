import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from functools import lru_cache

from app.core.config import get_settings


class SlidingWindowLimiter:
    """Скользящее окно в памяти процесса.

    Достаточно против брутфорса в рамках одной реплики API; при нескольких
    репликах лимит действует на каждую независимо (осознанное упрощение —
    без внешнего хранилища).
    """

    def __init__(self, max_attempts: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Регистрирует попытку. None — разрешено; иначе секунды до разблокировки."""
        now = self._clock()
        with self._lock:
            window = self._attempts[key]
            while window and now - window[0] >= self.window_seconds:
                window.popleft()
            if len(window) >= self.max_attempts:
                return self.window_seconds - (now - window[0])
            window.append(now)
            return None

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


@lru_cache
def get_login_limiter() -> SlidingWindowLimiter:
    settings = get_settings()
    return SlidingWindowLimiter(settings.login_rate_limit_attempts, settings.login_rate_limit_window_seconds)


@lru_cache
def get_register_limiter() -> SlidingWindowLimiter:
    settings = get_settings()
    return SlidingWindowLimiter(settings.register_rate_limit_attempts, settings.register_rate_limit_window_seconds)


@lru_cache
def get_forgot_password_limiter() -> SlidingWindowLimiter:
    settings = get_settings()
    return SlidingWindowLimiter(settings.forgot_rate_limit_attempts, settings.forgot_rate_limit_window_seconds)
