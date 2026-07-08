from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, require_role
from app.core.database import get_db
from app.models import CheckResult, Monitor, Organization
from app.schemas import CheckResultRead, MonitorCreate, MonitorRead, MonitorStatus, MonitorUpdate, MonitorUptimeRead
from app.services.audit import record
from app.services.config_sync import create_monitor_from_payload, persist_monitors_as_config, update_monitor_from_payload
from app.services.uptime import collect_uptime_stats

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
        confirmations=(monitor.config_json or {}).get("confirmations", 1),
        config=monitor.config_json or {},
    )


def get_org_monitor(db: Session, org: Organization, slug: str) -> Monitor:
    monitor = db.scalar(select(Monitor).where(Monitor.org_id == org.id, Monitor.slug == slug))
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return monitor


@router.get("/monitors", response_model=list[MonitorRead])
def list_monitors(
    ctx: OrgContext = Depends(get_current_org_member), db: Session = Depends(get_db)
) -> list[MonitorRead]:
    monitors = db.scalars(select(Monitor).where(Monitor.org_id == ctx.org.id).order_by(Monitor.slug)).all()
    return [to_monitor_read(monitor) for monitor in monitors]


@router.post("/monitors", response_model=MonitorRead, status_code=status.HTTP_201_CREATED)
def create_monitor(
    payload: MonitorCreate,
    ctx: OrgContext = Depends(require_role("member")),
    db: Session = Depends(get_db),
) -> MonitorRead:
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="monitor.create",
        entity="monitor",
        entity_id=payload.id,
        payload={"name": payload.name or payload.id, "type": payload.type},
    )
    return to_monitor_read(create_monitor_from_payload(db, ctx.user, ctx.org, payload))


# важно: статический путь /monitors/uptime регистрируется до динамического /monitors/{monitor_id}
@router.get("/monitors/uptime", response_model=list[MonitorUptimeRead])
def monitors_uptime(
    range: str = Query(default="24h", pattern=r"^(24h|7d|30d)$"),  # noqa: A002
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> list[MonitorUptimeRead]:
    since_map = {"24h": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    since = datetime.now(timezone.utc) - since_map[range]

    return [
        MonitorUptimeRead(
            monitor_id=row.slug,
            uptime_pct=row.uptime_pct,
            checks_total=row.checks_total,
            avg_response_ms=row.avg_response_ms,
            last_check_at=row.last_check_at,
            last_status=row.last_status,
            last_response_ms=row.last_response_ms,
        )
        for row in collect_uptime_stats(db, ctx.org.id, since)
    ]


@router.get("/monitors/{monitor_id}", response_model=MonitorRead)
def read_monitor(
    monitor_id: str,
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> MonitorRead:
    return to_monitor_read(get_org_monitor(db, ctx.org, monitor_id))


@router.put("/monitors/{monitor_id}", response_model=MonitorRead)
def update_monitor(
    monitor_id: str,
    payload: MonitorUpdate,
    ctx: OrgContext = Depends(require_role("member")),
    db: Session = Depends(get_db),
) -> MonitorRead:
    monitor = get_org_monitor(db, ctx.org, monitor_id)
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="monitor.update",
        entity="monitor",
        entity_id=monitor.slug,
        payload={"changes": sorted(payload.model_dump(exclude_unset=True))},
    )
    return to_monitor_read(update_monitor_from_payload(db, ctx.user, ctx.org, monitor, payload))


@router.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(
    monitor_id: str,
    ctx: OrgContext = Depends(require_role("member")),
    db: Session = Depends(get_db),
) -> None:
    monitor = get_org_monitor(db, ctx.org, monitor_id)
    monitor.enabled = False
    monitor.status = "paused"
    monitor.next_run_at = None
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="monitor.delete",
        entity="monitor",
        entity_id=monitor.slug,
        payload={"name": monitor.name},
    )
    persist_monitors_as_config(db, ctx.user, ctx.org)


@router.get("/history", response_model=list[CheckResultRead])
def history(
    monitor_id: str | None = None,
    range: str = Query(default="24h", pattern=r"^(1h|24h|7d|30d)$"),  # noqa: A002
    status_filter: MonitorStatus | None = Query(default=None, alias="status"),
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> list[CheckResultRead]:
    since_map = {"1h": timedelta(hours=1), "24h": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    query = select(CheckResult, Monitor).join(Monitor).where(
        Monitor.org_id == ctx.org.id,
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
