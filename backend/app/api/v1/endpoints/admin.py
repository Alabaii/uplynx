import logging
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_superuser
from app.core.config import get_settings
from app.core.database import get_db
from app.models import CheckResult, Incident, Monitor, Organization, OrgMember, Plan, SchedulerHeartbeat, User
from app.schemas import (
    AdminOrgRead,
    AdminOverview,
    AdminQueueDepth,
    AdminSchedulerStatus,
    OrgPlanUpdate,
    PlanRead,
    PlanUpdate,
)
from app.services.audit import record
from app.services.plans import apply_plan_downgrade, ensure_default_plans
from app.services.queue import BROWSER_QUEUE, DEAD_LETTER_QUEUES, HTTP_QUEUE, RabbitPublisher

logger = logging.getLogger(__name__)

router = APIRouter()


def get_publisher() -> Generator[RabbitPublisher, None, None]:
    # per-request подключение — как в monitors.py: BlockingConnection не потокобезопасен.
    # Закрытие в finally: без него каждый обзор оставлял бы висеть соединение с брокером
    publisher = RabbitPublisher()
    try:
        yield publisher
    finally:
        publisher.close()


def collect_queue_depths(publisher: RabbitPublisher) -> list[AdminQueueDepth] | None:
    """Глубины рабочих очередей и DLQ; None — RabbitMQ недоступен (не валим overview)."""
    try:
        depths = [
            AdminQueueDepth(name=queue, depth=publisher.check_queue_depth(queue))
            for queue in (HTTP_QUEUE, BROWSER_QUEUE)
        ]
        depths.extend(
            AdminQueueDepth(name=dead_queue, depth=publisher.declare_queue(dead_queue).method.message_count)
            for dead_queue in DEAD_LETTER_QUEUES.values()
        )
        return depths
    except Exception:  # noqa: BLE001 — любой сбой брокера не должен ломать обзор
        return None


def scheduler_status(db: Session) -> AdminSchedulerStatus:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    threshold = settings.scheduler_heartbeat_stale_seconds
    beat = db.get(SchedulerHeartbeat, 1)
    beat_age: int | None = None
    if beat is not None:
        beat_at = beat.beat_at if beat.beat_at.tzinfo else beat.beat_at.replace(tzinfo=timezone.utc)
        beat_age = int((now - beat_at).total_seconds())
    overdue = db.scalar(
        select(func.count())
        .select_from(Monitor)
        .where(Monitor.enabled.is_(True), Monitor.next_run_at < now - timedelta(seconds=threshold))
    ) or 0
    return AdminSchedulerStatus(
        beat_age_seconds=beat_age,
        stale=beat_age is None or beat_age > threshold,
        overdue_monitors=overdue,
    )


@router.get("/overview", response_model=AdminOverview)
def overview(
    _: User = Depends(require_superuser),
    db: Session = Depends(get_db),
    publisher: RabbitPublisher = Depends(get_publisher),
) -> AdminOverview:
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    return AdminOverview(
        users_total=db.scalar(select(func.count()).select_from(User)) or 0,
        orgs_total=db.scalar(select(func.count()).select_from(Organization)) or 0,
        # архивные мониторы в метриках платформы не считаем — они уже не работают
        monitors_total=db.scalar(
            select(func.count()).select_from(Monitor).where(Monitor.archived_at.is_(None))
        ) or 0,
        monitors_enabled=db.scalar(
            select(func.count())
            .select_from(Monitor)
            .where(Monitor.enabled.is_(True), Monitor.archived_at.is_(None))
        ) or 0,
        monitors_browser=db.scalar(
            select(func.count())
            .select_from(Monitor)
            .where(Monitor.type == "browser", Monitor.archived_at.is_(None))
        ) or 0,
        checks_24h=db.scalar(
            select(func.count()).select_from(CheckResult).where(CheckResult.timestamp >= day_ago)
        ) or 0,
        incidents_open=db.scalar(
            select(func.count()).select_from(Incident).where(Incident.status == "open")
        ) or 0,
        scheduler=scheduler_status(db),
        queues=collect_queue_depths(publisher),
    )


@router.get("/plans", response_model=list[PlanRead])
def list_plans(_: User = Depends(require_superuser), db: Session = Depends(get_db)) -> list[Plan]:
    ensure_default_plans(db)
    return list(db.scalars(select(Plan).order_by(Plan.sort_order)))


@router.put("/plans/{slug}", response_model=PlanRead)
def update_plan(
    slug: str,
    payload: PlanUpdate,
    user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> Plan:
    plan = db.get(Plan, slug)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    changes = payload.model_dump(exclude_unset=True, exclude={"unlimited_members"})
    if payload.unlimited_members:
        plan.max_members = None
        changes.pop("max_members", None)
    for field, value in changes.items():
        if value is not None:
            setattr(plan, field, value)
    plan.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    # платформенное событие: в org-scoped audit_log не пишем, фиксируем в логах процесса
    logger.info("plan %s updated by %s: %s", slug, user.email, changes or {"unlimited_members": True})
    return plan


@router.get("/orgs", response_model=list[AdminOrgRead])
def list_orgs(_: User = Depends(require_superuser), db: Session = Depends(get_db)) -> list[AdminOrgRead]:
    members = (
        select(OrgMember.org_id, func.count().label("members_count")).group_by(OrgMember.org_id).subquery()
    )
    monitors = (
        select(Monitor.org_id, func.count().label("monitors_count"))
        .where(Monitor.archived_at.is_(None))
        .group_by(Monitor.org_id)
        .subquery()
    )
    rows = db.execute(
        select(Organization, members.c.members_count, monitors.c.monitors_count)
        .outerjoin(members, members.c.org_id == Organization.id)
        .outerjoin(monitors, monitors.c.org_id == Organization.id)
        .order_by(Organization.id)
    ).all()
    return [
        AdminOrgRead(
            id=org.id,
            name=org.name,
            slug=org.slug,
            plan_slug=org.plan_slug,
            members_count=members_count or 0,
            monitors_count=monitors_count or 0,
            created_at=org.created_at,
        )
        for org, members_count, monitors_count in rows
    ]


@router.put("/orgs/{org_id}/plan", response_model=AdminOrgRead)
def set_org_plan(
    org_id: int,
    payload: OrgPlanUpdate,
    user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> AdminOrgRead:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    ensure_default_plans(db)
    if db.get(Plan, payload.plan_slug) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    previous = org.plan_slug
    org.plan_slug = payload.plan_slug
    # downgrade: мониторы сверх лимитов нового плана ставятся на паузу (не удаляются)
    paused = apply_plan_downgrade(db, org)
    record(
        db,
        org_id=org.id,
        user_id=user.id,
        action="org.plan_change",
        entity="org",
        entity_id=org.slug,
        payload={"from": previous, "to": payload.plan_slug, "paused_monitors": paused},
    )
    db.commit()
    members_count = db.scalar(select(func.count()).select_from(OrgMember).where(OrgMember.org_id == org.id)) or 0
    monitors_count = db.scalar(
        select(func.count())
        .select_from(Monitor)
        .where(Monitor.org_id == org.id, Monitor.archived_at.is_(None))
    ) or 0
    return AdminOrgRead(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan_slug=org.plan_slug,
        members_count=members_count,
        monitors_count=monitors_count,
        created_at=org.created_at,
        paused_monitors=paused,
    )
