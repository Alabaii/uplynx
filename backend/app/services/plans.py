from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Monitor, Organization, OrgMember, Plan

# Согласованная владельцем сетка (лимиты 2026-07-09; цены в копейках — рублёвый
# биллинг, 2026-07-10: Free 0 / Pro 990₽ / Business 3990₽). Дублирует сиды миграций
# 0018+0019: миграции наполняют прод-БД, этот сид — sqlite-тесты и старые томы.
DEFAULT_PLANS: tuple[dict, ...] = (
    {
        "slug": "free",
        "name": "Free",
        "price_monthly_kopeks": 0,
        "annual_discount_pct": 0,
        "max_monitors": 5,
        "min_interval_seconds": 300,
        "max_browser_monitors": 0,
        "browser_min_interval_seconds": 300,
        "max_members": 1,
        "retention_days": 30,
        "sort_order": 0,
    },
    {
        "slug": "pro",
        "name": "Pro",
        "price_monthly_kopeks": 99000,
        "annual_discount_pct": 17,
        "max_monitors": 50,
        "min_interval_seconds": 60,
        "max_browser_monitors": 5,
        "browser_min_interval_seconds": 300,
        "max_members": 5,
        "retention_days": 365,
        "sort_order": 1,
    },
    {
        "slug": "business",
        "name": "Business",
        "price_monthly_kopeks": 399000,
        "annual_discount_pct": 17,
        "max_monitors": 200,
        "min_interval_seconds": 10,
        "max_browser_monitors": 25,
        "browser_min_interval_seconds": 60,
        "max_members": None,
        "retention_days": 365,
        "sort_order": 2,
    },
)


def ensure_default_plans(db: Session) -> None:
    """Идемпотентный сид: наполняет plans дефолтами, только если таблица пуста."""
    if db.scalar(select(func.count()).select_from(Plan)):
        return
    for row in DEFAULT_PLANS:
        db.add(Plan(**row))
    db.commit()


def plan_gating_active() -> bool:
    """Лимиты тарифов применяются только в enterprise (SaaS-режим).

    team-редакция ограничена своими env-лимитами (TEAM_MAX_*); тарифы там
    декоративны — самостоятельный хостинг не должен упираться в SaaS-планы.
    """
    return get_settings().deployment_mode == "enterprise"


def get_org_plan(db: Session, org: Organization) -> Plan:
    """План организации; при отсутствующем slug откатывается на free."""
    ensure_default_plans(db)
    plan = db.get(Plan, org.plan_slug or "free") or db.get(Plan, "free")
    if plan is None:  # теоретически недостижимо после ensure_default_plans
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Plan catalog is empty")
    return plan


def min_interval_for(plan: Plan, monitor_type: str) -> int:
    return plan.browser_min_interval_seconds if monitor_type == "browser" else plan.min_interval_seconds


def validate_plan_interval(db: Session, org: Organization, monitor_type: str, interval: int) -> None:
    """400, если интервал чаще минимума плана (browser-проверки имеют свой минимум)."""
    if not plan_gating_active():
        return
    plan = get_org_plan(db, org)
    minimum = min_interval_for(plan, monitor_type)
    if interval < minimum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan '{plan.name}' allows {monitor_type} checks at most every {minimum} seconds",
        )


def enforce_plan_monitor_limits(db: Session, org: Organization, enabled_total: int, enabled_browser: int) -> None:
    """403, если счётчики enabled-мониторов ПОСЛЕ изменения превышают лимиты плана."""
    if not plan_gating_active():
        return
    plan = get_org_plan(db, org)
    if enabled_total > plan.max_monitors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan '{plan.name}' allows at most {plan.max_monitors} enabled monitors",
        )
    if enabled_browser > plan.max_browser_monitors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan '{plan.name}' allows at most {plan.max_browser_monitors} enabled browser monitors",
        )


def count_enabled_monitors(db: Session, org: Organization) -> tuple[int, int]:
    """(всего enabled, из них browser) — текущее состояние организации."""
    total = db.scalar(
        select(func.count())
        .select_from(Monitor)
        .where(Monitor.org_id == org.id, Monitor.enabled.is_(True), Monitor.archived_at.is_(None))
    ) or 0
    browser = db.scalar(
        select(func.count())
        .select_from(Monitor)
        .where(
            Monitor.org_id == org.id,
            Monitor.enabled.is_(True),
            Monitor.archived_at.is_(None),
            Monitor.type == "browser",
        )
    ) or 0
    return total, browser


def enforce_plan_member_limit(db: Session, org: Organization) -> None:
    """403 при явном добавлении участника сверх лимита плана.

    НЕ вызывается при регистрации: в этой архитектуре каждый новый пользователь
    попадает в default-организацию, и лимит плана заблокировал бы сам signup.
    """
    if not plan_gating_active():
        return
    plan = get_org_plan(db, org)
    if plan.max_members is None:
        return
    current = db.scalar(select(func.count()).select_from(OrgMember).where(OrgMember.org_id == org.id)) or 0
    if current + 1 > plan.max_members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan '{plan.name}' allows at most {plan.max_members} members",
        )


def apply_plan_downgrade(db: Session, org: Organization) -> list[str]:
    """Ставит на паузу мониторы сверх лимитов текущего плана организации.

    Ничего не удаляет: сверх общего лимита выключаются НОВЕЙШИЕ мониторы
    (старые — вероятнее ключевые), затем то же среди browser сверх их квоты.
    Интервалы не трогаем — минимум плана применяет шедулер на лету.
    Возвращает slug'и поставленных на паузу. Без commit — коммитит вызывающий.
    """
    if not plan_gating_active():
        return []
    plan = get_org_plan(db, org)
    enabled = list(
        db.scalars(
            select(Monitor)
            .where(Monitor.org_id == org.id, Monitor.enabled.is_(True), Monitor.archived_at.is_(None))
            .order_by(Monitor.created_at, Monitor.id)
        )
    )
    paused: list[Monitor] = []
    kept = enabled[: plan.max_monitors]
    paused.extend(enabled[plan.max_monitors:])
    browser_kept = [monitor for monitor in kept if monitor.type == "browser"]
    paused.extend(browser_kept[plan.max_browser_monitors:])
    for monitor in paused:
        monitor.enabled = False
        monitor.status = "paused"
        monitor.next_run_at = None
    return [monitor.slug for monitor in paused]
