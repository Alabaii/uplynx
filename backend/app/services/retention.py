import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CheckResult, Monitor, Organization, Plan, UptimeDaily
from app.services.plans import plan_gating_active

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


def retention_cutoffs(db: Session) -> list[tuple[datetime, list[int] | None]]:
    """Горизонты хранения сырых результатов: [(граница, org_id или None для всех)].

    Тариф задаёт retention_days, но применяется он только в enterprise: в team
    тарифы декоративны, и самостоятельный хостинг живёт на общем RETENTION_DAYS.
    Организации сгруппированы по значению срока — разных сроков единицы (по числу
    тарифов), поэтому сворачивание делается один раз на группу, а не на организацию.
    """
    now = datetime.now(timezone.utc)
    default_cutoff = now - timedelta(days=get_settings().retention_days)
    if not plan_gating_active():
        return [(default_cutoff, None)]

    rows = db.execute(
        select(Plan.retention_days, Organization.id).join(Organization, Organization.plan_slug == Plan.slug)
    ).all()
    by_days: dict[int, list[int]] = {}
    for retention_days, org_id in rows:
        by_days.setdefault(retention_days, []).append(org_id)
    groups: list[tuple[datetime, list[int] | None]] = [
        (now - timedelta(days=days), org_ids) for days, org_ids in by_days.items()
    ]
    # организации без строки плана (например, план удалён) — под общим горизонтом
    known = {org_id for org_ids in by_days.values() for org_id in org_ids}
    orphans = db.scalars(select(Organization.id).where(Organization.id.notin_(known))).all() if known else []
    if orphans or not groups:
        groups.append((default_cutoff, list(orphans) or None))
    return groups


def _prune_raw_results(db: Session, cutoff: datetime, org_ids: list[int] | None) -> int:
    """Удаляет сырые результаты старше cutoff, возвращает число удалённых строк.

    На PostgreSQL месячные партиции, целиком попавшие за горизонт ретеншена, дропаются
    целиком (дёшево); частично попавший месяц чистится обычным DELETE. На sqlite — только DELETE.
    Партицию можно дропнуть, только когда она просрочена для ВСЕХ организаций,
    поэтому дроп делается отдельно, по самому длинному сроку хранения.
    """
    delete_stmt = delete(CheckResult).where(CheckResult.timestamp < cutoff)
    if org_ids is not None:
        delete_stmt = delete_stmt.where(
            CheckResult.monitor_id.in_(select(Monitor.id).where(Monitor.org_id.in_(org_ids)))
        )
    return db.execute(delete_stmt).rowcount


def _drop_expired_partitions(db: Session, cutoff: datetime) -> int:
    """Дропает месячные партиции, полностью просроченные для всех организаций."""
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
    return pruned


def _rollup_group(db: Session, cutoff: datetime, org_ids: list[int] | None) -> int:
    """Сворачивает в uptime_daily всё старше cutoff у указанных организаций."""
    day = func.date(CheckResult.timestamp).label("day")
    query = (
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
    )
    if org_ids is not None:
        query = query.where(Monitor.org_id.in_(org_ids))
    groups = db.execute(query).all()

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

    return len(groups)


def rollup_and_prune(db: Session) -> tuple[int, int]:
    """Архивирует старые check_results в uptime_daily и удаляет сырые строки.

    Срок хранения сырой истории берётся из тарифа организации (в enterprise);
    суточные агрегаты не удаляются никогда — процент аптайма за прошлый год
    остаётся доступен и на тарифе с коротким хранением.

    Возвращает (сколько пар монитор-день заархивировано, сколько сырых строк удалено).
    Идемпотентно: агрегация и удаление идут в одной транзакции, повторный вызов
    не находит старых строк и ничего не меняет.
    """
    groups = retention_cutoffs(db)
    archived = sum(_rollup_group(db, cutoff, org_ids) for cutoff, org_ids in groups)
    # Сначала дроп целиком просроченных партиций — он снимает основную массу дёшево.
    # Партиция просрочена, только если она за горизонтом САМОГО ДЛИННОГО срока
    # хранения: иначе дроп унёс бы данные организации, которой ещё рано.
    pruned = _drop_expired_partitions(db, min(cutoff for cutoff, _ in groups))
    for cutoff, org_ids in groups:
        pruned += _prune_raw_results(db, cutoff, org_ids)
    db.commit()
    return archived, pruned
