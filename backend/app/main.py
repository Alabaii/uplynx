import asyncio
import logging
import time

from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import client_ip
from app.api.v1.router import api_router
from app.core.config import (
    get_settings,
    validate_cors_origins,
    validate_infrastructure_credentials,
    validate_jwt_secret,
    validate_secret_encryption_key,
)
from app.core.database import check_database, get_db
from app.core.observability import HTTP_REQUEST_SECONDS, HTTP_REQUESTS, init_sentry
from app.core.ratelimit import get_mutation_limiter
from app.core.security import decode_access_token
from app.models import Monitor, SchedulerHeartbeat

settings = get_settings()
validate_jwt_secret(settings)
validate_secret_encryption_key(settings)
validate_cors_origins(settings)
validate_infrastructure_credentials(settings)
init_sentry("api")

app = FastAPI(title=settings.app_name)


@app.middleware("http")
async def http_metrics(request: Request, call_next):  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    # шаблон маршрута ("/api/v1/monitors/{monitor_id}"), не сырой URL — иначе
    # каждая уникальная строка пути плодит отдельную метрику (cardinality)
    path = getattr(route, "path", None)
    if path and path != "/metrics":
        method = request.method
        HTTP_REQUESTS.labels(method=method, path=path, status=str(response.status_code)).inc()
        HTTP_REQUEST_SECONDS.labels(method=method, path=path).observe(time.perf_counter() - started)
    return response
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def mutation_rate_limit(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Rate-limit мутаций (гигиена): защищает от скриптового злоупотребления записью.

    /auth не трогаем — у логина/регистрации/восстановления свои, более строгие лимиты.
    Ключ — user id из access-токена (токен здесь только парсится, полноценная
    аутентификация остаётся за зависимостями эндпоинтов); без токена — IP:
    неавторизованные мутации всё равно упрутся в 401, но и им не даём молотить.
    """
    # scope["path"], а не request.url.path: последний пересобирается склейкой
    # "{scheme}://{host}{path}" и заново парсится, поэтому путь, не начинающийся
    # с "/" (например "@example.com"), сдвигает границу authority — .path
    # расходится с настоящим путём запроса, и лимитер молча пропускает мутацию.
    # Маршрутизация идёт по scope["path"], решение о лимите должно идти по нему же
    path = request.scope.get("path", "")
    if request.method in MUTATING_METHODS and path.startswith("/api/v1") and not path.startswith("/api/v1/auth"):
        auth_header = request.headers.get("authorization") or ""
        token = auth_header.removeprefix("Bearer ").strip()
        subject = decode_access_token(token) if token else None
        key = f"user:{subject}" if subject else f"ip:{client_ip(request)}"
        # лимитер ходит в БД синхронно, а middleware асинхронный: без отдельного
        # потока каждая мутация останавливала бы event loop всего процесса
        retry_after = await asyncio.to_thread(get_mutation_limiter().hit, key)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many changes, slow down"},
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    # в prod недоступен снаружи: nginx проксирует только /api, порт 8000 закрыт
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/ready")
def ready() -> JSONResponse:
    """Readiness: 503, если БД недоступна — на это вешается внешний проб.

    Именно 503, а не всплывшее исключение: 500 от readiness неотличим от
    обычной ошибки приложения, и в логах/алертах недоступность зависимости
    выглядела бы багом. Текст исключения наружу не отдаём — там строка
    подключения.
    """
    try:
        check_database()
    except Exception:  # noqa: BLE001 — любая ошибка подключения means "не готов"
        logging.getLogger(__name__).exception("readiness check failed")
        return JSONResponse(status_code=503, content={"status": "not ready"})
    return JSONResponse(content={"status": "ready"})


@app.get("/health/scheduler")
def scheduler_health(db: Session = Depends(get_db)) -> JSONResponse:
    """Liveness шедулера: 503, если heartbeat протух — цепляется внешним пробом.

    overdue_monitors — enabled-мониторы, чей next_run_at просрочен дольше порога:
    сигнал, что шедулер жив, но отстаёт (перегрузка/залипшая очередь).
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    threshold = settings.scheduler_heartbeat_stale_seconds

    beat = db.get(SchedulerHeartbeat, 1)
    if beat is None:
        healthy, lag_seconds, last_beat_at = False, None, None
    else:
        beat_at = beat.beat_at if beat.beat_at.tzinfo else beat.beat_at.replace(tzinfo=timezone.utc)
        lag_seconds = (now - beat_at).total_seconds()
        healthy = lag_seconds <= threshold
        last_beat_at = beat_at.isoformat()

    overdue = db.scalar(
        select(func.count())
        .select_from(Monitor)
        .where(Monitor.enabled.is_(True), Monitor.next_run_at < now - timedelta(seconds=threshold))
    ) or 0

    body = {
        "healthy": healthy,
        "last_beat_at": last_beat_at,
        "lag_seconds": lag_seconds,
        "overdue_monitors": overdue,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
