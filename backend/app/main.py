from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.core.config import get_settings, validate_jwt_secret
from app.core.database import check_database, get_db
from app.models import Monitor, SchedulerHeartbeat

settings = get_settings()
validate_jwt_secret(settings)

app = FastAPI(title=settings.app_name)
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


@app.get("/ready")
def ready() -> dict[str, str]:
    check_database()
    return {"status": "ready"}


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
