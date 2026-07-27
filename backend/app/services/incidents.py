from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, Monitor

# severity: down хуже degraded — фиксируем худшее наблюдённое за инцидент
_SEVERITY_RANK = {"degraded": 1, "down": 2}


def _open_incident(db: Session, monitor_id: int) -> Incident | None:
    return db.scalar(select(Incident).where(Incident.monitor_id == monitor_id, Incident.status == "open"))


def _close(incident: Incident, now: datetime) -> None:
    started = incident.started_at
    if started.tzinfo is None:  # sqlite отдаёт naive datetime
        started = started.replace(tzinfo=timezone.utc)
    incident.status = "resolved"
    incident.resolved_at = now
    incident.duration_seconds = int((now - started).total_seconds())


def resolve_open_incident(db: Session, monitor_id: int) -> Incident | None:
    """Закрывает открытый инцидент монитора, который перестал проверяться.

    Обычно инцидент закрывает пайплайн проверок, когда монитор возвращается в up.
    Но монитор останавливают и снаружи пайплайна — паузой, архивацией, ресинком
    конфига, даунгрейдом тарифа, — и после этого проверок не будет вообще:
    инцидент оставался бы открытым навсегда. В списке организации он висел бы
    незакрытым, а incidents_open в админке переставал бы что-либо значить как
    метрика платформы, монотонно накапливая мониторы, которых уже нет.

    Возвращает закрытый инцидент или None, если открытого не было.
    Коммит — на стороне вызывающего.
    """
    incident = _open_incident(db, monitor_id)
    if incident is None:
        return None
    _close(incident, datetime.now(timezone.utc))
    return incident


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
            _close(incident, now)
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
