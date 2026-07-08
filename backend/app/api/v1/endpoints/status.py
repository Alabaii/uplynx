from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Monitor, Organization
from app.schemas import PublicOverallStatus, PublicStatusMonitor, PublicStatusRead
from app.services.uptime import collect_uptime_stats

router = APIRouter()


def overall_status(statuses: set[str]) -> PublicOverallStatus:
    # pending/paused не влияют на общий статус
    if "down" in statuses:
        return "down"
    if "degraded" in statuses:
        return "degraded"
    return "operational"


@router.get("/{org_slug}", response_model=PublicStatusRead)
def public_status(org_slug: str, db: Session = Depends(get_db)) -> PublicStatusRead:
    """Публичная статус-страница: без авторизации, только имена и статусы мониторов.

    RLS: app.org_id не выставлен (нет get_current_org_member) — политика пропускает,
    поэтому фильтрация по org_id во всех запросах явная.
    """
    org = db.scalar(select(Organization).where(Organization.slug == org_slug))
    if not org or not org.status_page_enabled:
        # выключенная страница неотличима от несуществующей организации
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status page not found")

    monitors = db.scalars(
        select(Monitor).where(Monitor.org_id == org.id, Monitor.enabled.is_(True)).order_by(Monitor.slug)
    ).all()
    since = datetime.now(timezone.utc) - timedelta(days=1)
    stats = {row.monitor_id: row for row in collect_uptime_stats(db, org.id, since)}

    return PublicStatusRead(
        organization=org.name,
        updated_at=datetime.now(timezone.utc),
        overall=overall_status({monitor.status for monitor in monitors}),
        monitors=[
            PublicStatusMonitor(
                name=monitor.name,
                status=monitor.status,
                uptime_pct=stats[monitor.id].uptime_pct if monitor.id in stats else None,
                last_check_at=stats[monitor.id].last_check_at if monitor.id in stats else None,
            )
            for monitor in monitors
        ],
    )
