import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CheckResult, Monitor, UptimeDaily

# месячные партиции check_results (только postgres): check_results_YYYY_MM
PARTITION_NAME_RE = re.compile(r"^check_results_(\d{4})_(\d{2})$")


def _month_start(anchor: date, offset: int = 0) -> date:
    total = anchor.year * 12 + (anchor.month - 1) + offset
    return date(total // 12, total % 12 + 1, 1)


def _partition_ddl(start: date) -> str:
    end = _month_start(start, 1)
    name = f"check_results_{start.year:04d}_{start.month:02d}"
    return (
        f'CREATE TABLE IF NOT EXISTS "{name}" PARTITION OF check_results '
        f"FOR VALUES FROM ('{start.isoformat()} 00:00:00+00') TO ('{end.isoformat()} 00:00:00+00')"
    )


def ensure_partitions(db: Session) -> None:
    """Создаёт месячные партиции check_results на текущий и следующий месяц (только PostgreSQL)."""
    if db.get_bind().dialect.name != "postgresql":
        return
    today = datetime.now(timezone.utc).date()
    for offset in (0, 1):
        db.execute(text(_partition_ddl(_month_start(today, offset))))
    db.commit()


def _prune_raw_results(db: Session, cutoff: datetime) -> int:
    """Удаляет сырые результаты старше cutoff, возвращает число удалённых строк.

    На PostgreSQL месячные партиции, целиком попавшие за горизонт ретеншена, дропаются
    целиком (дёшево); частично попавший месяц чистится обычным DELETE. На sqlite — только DELETE.
    """
    pruned = 0
    if db.get_bind().dialect.name == "postgresql":
        rows = db.execute(
            text(
                "SELECT c.relname FROM pg_inherits i "
                "JOIN pg_class c ON c.oid = i.inhrelid "
                "JOIN pg_class p ON p.oid = i.inhparent "
                "WHERE p.relname = 'check_results'"
            )
        ).all()
        for (name,) in rows:
            match = PARTITION_NAME_RE.match(name)
            if not match:
                continue
            upper = _month_start(date(int(match.group(1)), int(match.group(2)), 1), 1)
            if datetime(upper.year, upper.month, upper.day, tzinfo=timezone.utc) <= cutoff:
                pruned += db.execute(text(f'SELECT count(*) FROM "{name}"')).scalar() or 0
                db.execute(text(f'DROP TABLE "{name}"'))
    pruned += db.execute(delete(CheckResult).where(CheckResult.timestamp < cutoff)).rowcount
    return pruned


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

    pruned = _prune_raw_results(db, cutoff)
    db.commit()
    return len(groups), pruned
