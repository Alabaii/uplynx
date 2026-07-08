from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CheckResult, Monitor, User
from app.schemas import CheckResultRead, MonitorCreate, MonitorRead, MonitorStatus, MonitorUpdate
from app.services.config_sync import create_monitor_from_payload, persist_monitors_as_config, update_monitor_from_payload

router = APIRouter()


def to_monitor_read(monitor: Monitor) -> MonitorRead:
    return MonitorRead(
        id=monitor.slug,
        internal_id=monitor.id,
        name=monitor.name,
        type=monitor.type,
        status=monitor.status,
        url=monitor.url,
        interval=monitor.interval,
        enabled=monitor.enabled,
        config=monitor.config_json or {},
    )


def get_owned_monitor(db: Session, user: User, slug: str) -> Monitor:
    monitor = db.scalar(select(Monitor).where(Monitor.user_id == user.id, Monitor.slug == slug))
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return monitor


@router.get("/monitors", response_model=list[MonitorRead])
def list_monitors(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[MonitorRead]:
    monitors = db.scalars(select(Monitor).where(Monitor.user_id == user.id).order_by(Monitor.slug)).all()
    return [to_monitor_read(monitor) for monitor in monitors]


@router.post("/monitors", response_model=MonitorRead, status_code=status.HTTP_201_CREATED)
def create_monitor(
    payload: MonitorCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonitorRead:
    return to_monitor_read(create_monitor_from_payload(db, user, payload))


@router.get("/monitors/{monitor_id}", response_model=MonitorRead)
def read_monitor(
    monitor_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonitorRead:
    return to_monitor_read(get_owned_monitor(db, user, monitor_id))


@router.put("/monitors/{monitor_id}", response_model=MonitorRead)
def update_monitor(
    monitor_id: str,
    payload: MonitorUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonitorRead:
    monitor = get_owned_monitor(db, user, monitor_id)
    return to_monitor_read(update_monitor_from_payload(db, user, monitor, payload))


@router.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(
    monitor_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    monitor = get_owned_monitor(db, user, monitor_id)
    monitor.enabled = False
    monitor.status = "paused"
    monitor.next_run_at = None
    persist_monitors_as_config(db, user)


@router.get("/history", response_model=list[CheckResultRead])
def history(
    monitor_id: str | None = None,
    range: str = Query(default="24h", pattern=r"^(1h|24h|7d|30d)$"),  # noqa: A002
    status_filter: MonitorStatus | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CheckResultRead]:
    since_map = {"1h": timedelta(hours=1), "24h": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    query = select(CheckResult, Monitor).join(Monitor).where(
        Monitor.user_id == user.id,
        CheckResult.timestamp >= datetime.now(timezone.utc) - since_map[range],
    )
    if monitor_id:
        query = query.where(Monitor.slug == monitor_id)
    if status_filter:
        query = query.where(CheckResult.status == status_filter)
    rows = db.execute(query.order_by(CheckResult.timestamp.desc()).limit(500)).all()
    return [
        CheckResultRead(
            id=result.id,
            monitor_id=result.monitor_id,
            monitor_slug=monitor.slug,
            status=result.status,
            response_time_ms=result.response_time_ms,
            error=result.error,
            details=result.details or {},
            timestamp=result.timestamp,
        )
        for result, monitor in rows
    ]
