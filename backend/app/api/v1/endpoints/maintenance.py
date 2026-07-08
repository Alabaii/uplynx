from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, require_role
from app.core.database import get_db
from app.models import MaintenanceWindow, Monitor, User
from app.schemas import MaintenanceWindowCreate, MaintenanceWindowRead
from app.services.audit import record

router = APIRouter()


def as_utc(value: datetime) -> datetime:
    # sqlite возвращает naive-даты, postgres — aware; храним и сравниваем в UTC
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def to_window_read(
    window: MaintenanceWindow,
    monitor_slug: str | None,
    monitor_name: str | None,
    created_by_email: str | None,
    now: datetime,
) -> MaintenanceWindowRead:
    return MaintenanceWindowRead(
        id=window.id,
        monitor_id=monitor_slug,
        monitor_name=monitor_name,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        note=window.note,
        active=as_utc(window.starts_at) <= now < as_utc(window.ends_at),
        created_by_email=created_by_email,
    )


@router.get("", response_model=list[MaintenanceWindowRead])
def list_maintenance(
    include_past: bool = Query(default=False),
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> list[MaintenanceWindowRead]:
    now = datetime.now(timezone.utc)
    query = (
        select(MaintenanceWindow, Monitor.slug, Monitor.name, User.email)
        .outerjoin(Monitor, Monitor.id == MaintenanceWindow.monitor_id)
        .outerjoin(User, User.id == MaintenanceWindow.created_by)
        .where(MaintenanceWindow.org_id == ctx.org.id)
    )
    if not include_past:
        query = query.where(MaintenanceWindow.ends_at >= now - timedelta(days=7))
    rows = db.execute(query.order_by(MaintenanceWindow.starts_at.desc())).all()
    return [to_window_read(window, slug, name, email, now) for window, slug, name, email in rows]


@router.post("", response_model=MaintenanceWindowRead, status_code=status.HTTP_201_CREATED)
def create_maintenance(
    payload: MaintenanceWindowCreate,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> MaintenanceWindowRead:
    monitor = None
    if payload.monitor_id is not None:
        monitor = db.scalar(
            select(Monitor).where(Monitor.org_id == ctx.org.id, Monitor.slug == payload.monitor_id)
        )
        if not monitor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    window = MaintenanceWindow(
        org_id=ctx.org.id,
        monitor_id=monitor.id if monitor else None,
        starts_at=as_utc(payload.starts_at),
        ends_at=as_utc(payload.ends_at),
        note=payload.note,
        created_by=ctx.user.id,
    )
    db.add(window)
    db.flush()
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="maintenance.create",
        entity="maintenance",
        entity_id=str(window.id),
        payload={
            "monitor": monitor.slug if monitor else "all",
            "starts_at": window.starts_at.isoformat(),
            "ends_at": window.ends_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(window)
    return to_window_read(
        window,
        monitor.slug if monitor else None,
        monitor.name if monitor else None,
        ctx.user.email,
        datetime.now(timezone.utc),
    )


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance(
    window_id: int,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    window = db.scalar(
        select(MaintenanceWindow).where(
            MaintenanceWindow.id == window_id, MaintenanceWindow.org_id == ctx.org.id
        )
    )
    if not window:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance window not found")
    monitor_slug = (
        db.scalar(select(Monitor.slug).where(Monitor.id == window.monitor_id)) if window.monitor_id else None
    )
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="maintenance.delete",
        entity="maintenance",
        entity_id=str(window.id),
        payload={"monitor": monitor_slug or "all"},
    )
    # проверки затронутых мониторов уже перенесены на конец окна — возвращаем их сразу,
    # иначе после отмены длинного окна монитор молчал бы до его планового конца
    now = datetime.now(timezone.utc)
    if as_utc(window.ends_at) > now:
        affected = select(Monitor).where(Monitor.org_id == ctx.org.id, Monitor.enabled.is_(True))
        if window.monitor_id is not None:
            affected = affected.where(Monitor.id == window.monitor_id)
        for monitor in db.scalars(affected):
            if monitor.next_run_at is not None and as_utc(monitor.next_run_at) > now:
                monitor.next_run_at = now
    db.delete(window)
    db.commit()
