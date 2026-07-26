from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models import CheckResult, Monitor


@dataclass(frozen=True)
class MonitorUptimeStats:
    monitor_id: int
    slug: str
    uptime_pct: float | None
    checks_total: int
    avg_response_ms: int | None
    last_check_at: datetime | None
    last_status: str | None
    last_response_ms: int | None


def collect_uptime_stats(db: Session, org_id: int, since: datetime) -> list[MonitorUptimeStats]:
    """Агрегаты uptime по всем мониторам организации начиная с since.

    Используется и авторизованным GET /monitors/uptime, и публичной статус-страницей,
    где app.org_id не выставлен (RLS пропускает) — фильтр по org_id здесь явный.
    """
    stats = db.execute(
        select(
            Monitor.id,
            Monitor.slug,
            func.count(CheckResult.id).label("checks_total"),
            func.sum(case((CheckResult.status == "up", 1), else_=0)).label("checks_up"),
            func.avg(CheckResult.response_time_ms).label("avg_response_ms"),
        )
        .outerjoin(CheckResult, and_(CheckResult.monitor_id == Monitor.id, CheckResult.timestamp >= since))
        .where(Monitor.org_id == org_id, Monitor.archived_at.is_(None))
        .group_by(Monitor.id, Monitor.slug)
        .order_by(Monitor.slug)
    ).all()

    last_rank = (
        func.row_number()
        .over(partition_by=CheckResult.monitor_id, order_by=(CheckResult.timestamp.desc(), CheckResult.id.desc()))
        .label("last_rank")
    )
    ranked = (
        select(CheckResult.monitor_id, CheckResult.timestamp, CheckResult.status, CheckResult.response_time_ms, last_rank)
        .join(Monitor, Monitor.id == CheckResult.monitor_id)
        .where(Monitor.org_id == org_id, Monitor.archived_at.is_(None), CheckResult.timestamp >= since)
        .subquery()
    )
    last_checks = {row.monitor_id: row for row in db.execute(select(ranked).where(ranked.c.last_rank == 1)).all()}

    uptime = []
    for row in stats:
        last = last_checks.get(row.id)
        uptime.append(
            MonitorUptimeStats(
                monitor_id=row.id,
                slug=row.slug,
                uptime_pct=round(row.checks_up / row.checks_total * 100, 1) if row.checks_total else None,
                checks_total=row.checks_total,
                avg_response_ms=round(row.avg_response_ms) if row.avg_response_ms is not None else None,
                last_check_at=last.timestamp if last else None,
                last_status=last.status if last else None,
                last_response_ms=last.response_time_ms if last else None,
            )
        )
    return uptime
