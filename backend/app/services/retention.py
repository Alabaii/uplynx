from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CheckResult, Monitor, UptimeDaily


def rollup_and_prune(db: Session) -> tuple[int, int]:
    """Архивирует check_results старше retention_days в uptime_daily и удаляет сырые строки.

    Возвращает (сколько пар монитор-день заархивировано, сколько сырых строк удалено).
    Идемпотентно: агрегация и удаление идут в одной транзакции, повторный вызов
    не находит старых строк и ничего не меняет.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().retention_days)

    day = func.date(CheckResult.timestamp).label("day")
    groups = db.execute(
        select(
            CheckResult.monitor_id,
            Monitor.org_id,
            day,
            func.count(CheckResult.id).label("checks_total"),
            func.sum(case((CheckResult.status == "up", 1), else_=0)).label("checks_up"),
            func.sum(case((CheckResult.status == "degraded", 1), else_=0)).label("checks_degraded"),
            func.sum(case((CheckResult.status == "down", 1), else_=0)).label("checks_down"),
            func.avg(CheckResult.response_time_ms).label("avg_response_ms"),
        )
        .join(Monitor, Monitor.id == CheckResult.monitor_id)
        .where(CheckResult.timestamp < cutoff)
        .group_by(CheckResult.monitor_id, Monitor.org_id, day)
    ).all()

    for row in groups:
        # sqlite отдаёт date() строкой, postgres — датой
        bucket_date = row.day if isinstance(row.day, date) else date.fromisoformat(row.day)
        avg_ms = round(row.avg_response_ms) if row.avg_response_ms is not None else None
        existing = db.scalar(
            select(UptimeDaily).where(UptimeDaily.monitor_id == row.monitor_id, UptimeDaily.date == bucket_date)
        )
        if existing is None:
            db.add(
                UptimeDaily(
                    org_id=row.org_id,
                    monitor_id=row.monitor_id,
                    date=bucket_date,
                    checks_total=row.checks_total,
                    checks_up=row.checks_up,
                    checks_degraded=row.checks_degraded,
                    checks_down=row.checks_down,
                    avg_response_ms=avg_ms,
                )
            )
        else:
            # день мог попасть под ретеншен частями — объединяем со старым агрегатом
            if avg_ms is not None and existing.avg_response_ms is not None:
                total = existing.checks_total + row.checks_total
                existing.avg_response_ms = round(
                    (existing.avg_response_ms * existing.checks_total + avg_ms * row.checks_total) / total
                )
            elif avg_ms is not None:
                existing.avg_response_ms = avg_ms
            existing.checks_total += row.checks_total
            existing.checks_up += row.checks_up
            existing.checks_degraded += row.checks_degraded
            existing.checks_down += row.checks_down

    pruned = db.execute(delete(CheckResult).where(CheckResult.timestamp < cutoff)).rowcount
    db.commit()
    return len(groups), pruned
