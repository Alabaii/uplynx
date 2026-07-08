from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, Monitor

# severity: down хуже degraded — фиксируем худшее наблюдённое за инцидент
_SEVERITY_RANK = {"degraded": 1, "down": 2}


def _open_incident(db: Session, monitor_id: int) -> Incident | None:
    return db.scalar(select(Incident).where(Incident.monitor_id == monitor_id, Incident.status == "open"))


def update_incident_for_status_change(
    db: Session, monitor: Monitor, new_effective_status: str, error: str | None
) -> None:
    """Открывает/эскалирует/закрывает инцидент при РЕАЛЬНОЙ смене эффективного статуса.

    Вызывать только когда эффективный статус монитора действительно сменился.
    Коммит — на стороне вызывающего (та же транзакция, что и CheckResult/статус).
    """
    now = datetime.now(timezone.utc)

    if new_effective_status == "up":
        incident = _open_incident(db, monitor.id)
        if incident is not None:
            started = incident.started_at
            if started.tzinfo is None:  # sqlite отдаёт naive datetime
                started = started.replace(tzinfo=timezone.utc)
            incident.status = "resolved"
            incident.resolved_at = now
            incident.duration_seconds = int((now - started).total_seconds())
        return

    if new_effective_status in ("down", "degraded"):
        incident = _open_incident(db, monitor.id)
        if incident is not None:
            if _SEVERITY_RANK[new_effective_status] > _SEVERITY_RANK[incident.severity]:
                incident.severity = new_effective_status
        else:
            db.add(
                Incident(
                    org_id=monitor.org_id,
                    monitor_id=monitor.id,
                    status="open",
                    severity=new_effective_status,
                    started_at=now,
                    trigger_error=error,
                )
            )
        return

    # pending — ничего не делаем
