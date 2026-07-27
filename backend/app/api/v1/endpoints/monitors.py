from datetime import datetime, timedelta, timezone

import pika
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, require_role
from app.core.config import get_settings
from app.core.database import get_db
from app.core.ratelimit import DatabaseRateLimiter
from app.models import CheckResult, MaintenanceWindow, Monitor, Organization
from app.schemas import (
    CheckNowRead,
    CheckResultRead,
    MonitorCreate,
    MonitorRead,
    MonitorStatus,
    MonitorUpdate,
    MonitorUptimeRead,
)
from app.services.audit import record
from app.services.config_sync import create_monitor_from_payload, persist_monitors_as_config, update_monitor_from_payload
from app.services.plans import get_org_plan, min_interval_for, plan_gating_active
from app.services.queue import RabbitPublisher, task_for_monitor
from app.services.uptime import collect_uptime_stats

router = APIRouter()


def get_publisher() -> RabbitPublisher:
    # per-request подключение: pika BlockingConnection не потокобезопасен,
    # а sync-эндпоинты FastAPI выполняются в пуле потоков
    return RabbitPublisher()


def ssl_days_left(monitor: Monitor) -> int | None:
    if monitor.ssl_expires_at is None:
        return None
    expires = monitor.ssl_expires_at
    if expires.tzinfo is None:  # sqlite отдаёт naive datetime
        expires = expires.replace(tzinfo=timezone.utc)
    return (expires - datetime.now(timezone.utc)).days


def to_monitor_read(monitor: Monitor, in_maintenance: bool = False) -> MonitorRead:
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
        in_maintenance=in_maintenance,
        ssl_expires_at=monitor.ssl_expires_at,
        ssl_days_left=ssl_days_left(monitor),
    )


def active_maintenance_monitor_ids(db: Session, org_id: int, now: datetime) -> set[int | None]:
    """monitor_id активных окон обслуживания организации; None в множестве — окно на всю организацию."""
    return set(
        db.scalars(
            select(MaintenanceWindow.monitor_id).where(
                MaintenanceWindow.org_id == org_id,
                MaintenanceWindow.starts_at <= now,
                MaintenanceWindow.ends_at > now,
            )
        ).all()
    )


def enforce_manual_check_interval(db: Session, org: Organization, monitor: Monitor) -> None:
    """Ручная проверка подчиняется минимальному интервалу тарифа.

    Кнопка «проверить сейчас» публикует ту же задачу, что шедулер, только мимо
    расписания — и без этого лимита частоту обращений к цели задавал не тариф,
    а общий потолок мутаций (60 в минуту). Для browser-проверок это к тому же
    занимало оба слота единственного воркера в ущерб остальным организациям.

    В team-режиме тарифы декоративны (инсталляция обслуживает одну команду),
    поэтому ограничение действует только в enterprise.
    """
    if not plan_gating_active():
        return
    plan = get_org_plan(db, org)
    minimum = min_interval_for(plan, monitor.type)
    # окно = минимум плана, одна попытка: счётчик общий для реплик, как у входа
    limiter = DatabaseRateLimiter("check_now", max_attempts=1, window_seconds=minimum)
    retry_after = limiter.hit(f"{org.id}:{monitor.id}")
    if retry_after is None:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Plan '{plan.name}' allows one manual {monitor.type} check every {minimum} seconds",
        headers={"Retry-After": str(int(retry_after) + 1)},
    )


def get_org_monitor(db: Session, org: Organization, slug: str) -> Monitor:
    # архивный монитор для API не существует: слаг мог быть занят заново
    monitor = db.scalar(
        select(Monitor).where(
            Monitor.org_id == org.id, Monitor.slug == slug, Monitor.archived_at.is_(None)
        )
    )
    if not monitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return monitor


@router.get("/monitors", response_model=list[MonitorRead])
def list_monitors(
    ctx: OrgContext = Depends(get_current_org_member), db: Session = Depends(get_db)
) -> list[MonitorRead]:
    monitors = db.scalars(
        select(Monitor)
        .where(Monitor.org_id == ctx.org.id, Monitor.archived_at.is_(None))
        .order_by(Monitor.slug)
    ).all()
    # один запрос активных окон на весь список — без N+1
    in_maintenance_ids = active_maintenance_monitor_ids(db, ctx.org.id, datetime.now(timezone.utc))
    org_wide = None in in_maintenance_ids
    return [
        to_monitor_read(monitor, in_maintenance=org_wide or monitor.id in in_maintenance_ids)
        for monitor in monitors
    ]


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


@router.post("/monitors/{monitor_id}/check", response_model=CheckNowRead, status_code=status.HTTP_202_ACCEPTED)
def check_monitor_now(
    monitor_id: str,
    ctx: OrgContext = Depends(require_role("member")),
    db: Session = Depends(get_db),
    publisher: RabbitPublisher = Depends(get_publisher),
) -> CheckNowRead:
    monitor = get_org_monitor(db, ctx.org, monitor_id)
    if not monitor.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Monitor is disabled")
    in_maintenance_ids = active_maintenance_monitor_ids(db, ctx.org.id, datetime.now(timezone.utc))
    if None in in_maintenance_ids or monitor.id in in_maintenance_ids:
        # внеплановая проверка в окне обслуживания портила бы статистику и будила алерты
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Monitor is in maintenance")
    enforce_manual_check_interval(db, ctx.org, monitor)
    task = task_for_monitor(monitor, timeout_seconds=get_settings().check_timeout_seconds)
    try:
        publisher.publish(task)
    except pika.exceptions.AMQPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Check queue is unavailable"
        ) from exc
    finally:
        publisher.close()
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="monitor.check_now",
        entity="monitor",
        entity_id=monitor.slug,
        payload={"task_id": task.task_id},
    )
    db.commit()
    return CheckNowRead(queued=True, task_id=task.task_id)


@router.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(
    monitor_id: str,
    ctx: OrgContext = Depends(require_role("member")),
    db: Session = Depends(get_db),
) -> None:
    """Архивирует монитор: он исчезает из продукта и освобождает слаг.

    Строка и история проверок остаются в БД — удаление не рвёт внешние ключи
    и остаётся восстановимым. Пауза (enabled=false) — отдельное действие.
    """
    monitor = get_org_monitor(db, ctx.org, monitor_id)
    monitor.archived_at = datetime.now(timezone.utc)
    monitor.enabled = False
    monitor.status = "paused"
    monitor.next_run_at = None
    # сессия с autoflush=False: без flush снимок конфига ниже увидит монитор живым
    db.flush()
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
        Monitor.archived_at.is_(None),
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
