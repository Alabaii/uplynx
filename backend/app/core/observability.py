"""Наблюдаемость: Sentry (ошибки) и Prometheus (метрики).

Sentry активируется только при заданном SENTRY_DSN — без него init_sentry
безвреден (no-op), поэтому модуль безопасен для dev/self-hosted.

Метрики каждый процесс отдаёт сам: API — роутом /metrics (в prod не проксируется
nginx и порт закрыт), scheduler/воркеры — встроенным HTTP-сервером на
METRICS_PORT (0 = выключен; в compose порты не публикуются наружу).
"""
import logging

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# --- метрики (общий реестр процесса; каждый процесс экспортирует свои) ---------------------------

CHECKS_PROCESSED = Counter(
    "uplynx_checks_processed_total",
    "Обработанные воркером задачи проверок",
    ["queue", "result"],  # result: up/down/degraded/pending | error (сбой обработки)
)
CHECK_PROCESSING_SECONDS = Histogram(
    "uplynx_check_processing_seconds",
    "Длительность обработки одной задачи воркером (проверка + запись результата)",
    ["queue"],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
CHECKS_DEAD_LETTERED = Counter(
    "uplynx_checks_dead_lettered_total",
    "Задачи, отклонённые воркером в dead-letter queue",
    ["queue"],
)
SCHEDULER_PUBLISHED = Counter(
    "uplynx_scheduler_published_total",
    "Задачи, опубликованные шедулером в очереди",
)
SCHEDULER_OVERDUE_MONITORS = Gauge(
    "uplynx_scheduler_overdue_monitors",
    "Enabled-мониторы с просроченным next_run_at (шедулер отстаёт)",
)
DLQ_DEPTH = Gauge(
    "uplynx_dlq_depth",
    "Глубина dead-letter queue (обновляется шедулером каждый тик)",
    ["queue"],
)
HTTP_REQUESTS = Counter(
    "uplynx_http_requests_total",
    "HTTP-запросы к API",
    ["method", "path", "status"],
)
HTTP_REQUEST_SECONDS = Histogram(
    "uplynx_http_request_seconds",
    "Длительность HTTP-запросов к API",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)


def init_sentry(component: str) -> bool:
    """Инициализирует Sentry для процесса; False — DSN не задан, ничего не делаем.

    logging-интеграция sentry-sdk по умолчанию отправляет записи уровня ERROR,
    поэтому существующие logger.exception(...) попадают в Sentry без правок кода.
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    sentry_sdk.set_tag("component", component)
    logger.info("sentry enabled for %s (environment=%s)", component, settings.environment)
    return True


def start_metrics_server() -> bool:
    """Поднимает HTTP-сервер /metrics для не-API процессов; False — METRICS_PORT=0."""
    port = get_settings().metrics_port
    if not port:
        return False
    start_http_server(port)
    logger.info("prometheus metrics on :%s/metrics", port)
    return True
