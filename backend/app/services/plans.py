from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Plan

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
