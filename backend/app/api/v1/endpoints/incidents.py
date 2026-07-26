from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member
from app.core.database import get_db
from app.models import Incident, Monitor
from app.schemas import IncidentRead, IncidentStatus

router = APIRouter()

_SINCE_MAP = {"24h": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def to_incident_read(incident: Incident, monitor_slug: str, monitor_name: str) -> IncidentRead:
    return IncidentRead(
        id=incident.id,
        monitor_slug=monitor_slug,
        monitor_name=monitor_name,
        status=incident.status,
        severity=incident.severity,
        started_at=incident.started_at,
        resolved_at=incident.resolved_at,
        duration_seconds=incident.duration_seconds,
        trigger_error=incident.trigger_error,
    )


@router.get("/incidents", response_model=list[IncidentRead])
def list_incidents(
    monitor_id: str | None = None,
    status_filter: IncidentStatus | None = Query(default=None, alias="status"),
    range: str = Query(default="7d", pattern=r"^(24h|7d|30d)$"),  # noqa: A002
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> list[IncidentRead]:
    query = (
        select(Incident, Monitor.slug, Monitor.name)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .where(
            Incident.org_id == ctx.org.id,
            Monitor.archived_at.is_(None),
            Incident.started_at >= datetime.now(timezone.utc) - _SINCE_MAP[range],
        )
    )
    if monitor_id:
        query = query.where(Monitor.slug == monitor_id)
    if status_filter:
        query = query.where(Incident.status == status_filter)
    rows = db.execute(query.order_by(Incident.started_at.desc()).limit(limit).offset(offset)).all()
    return [to_incident_read(incident, slug, name) for incident, slug, name in rows]


# путь с суффиксом /incidents не конфликтует с /monitors/uptime и /monitors/{monitor_id}
@router.get("/monitors/{monitor_id}/incidents", response_model=list[IncidentRead])
def monitor_incidents(
    monitor_id: str,
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> list[IncidentRead]:
    monitor = db.scalar(select(Monitor).where(Monitor.org_id == ctx.org.id, Monitor.slug == monitor_id))
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    incidents = db.scalars(
        select(Incident).where(Incident.monitor_id == monitor.id).order_by(Incident.started_at.desc()).limit(50)
    ).all()
    return [to_incident_read(incident, monitor.slug, monitor.name) for incident in incidents]
