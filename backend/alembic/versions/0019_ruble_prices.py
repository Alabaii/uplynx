"""plans: цены в рублях (копейки) вместо долларовых центов

Решение владельца (2026-07-10): приём платежей в рублях через российский
провайдер (ЮKassa/Robokassa), Stripe отменён. Колонка переименовывается в
price_monthly_kopeks, а значения дефолтных планов заменяются на рублёвую сетку:
старые числа — долларовые центы, в копейках они бессмысленны, конвертация
курсом дала бы некруглые цены. Кастомные значения, введённые в админке до этой
миграции, тоже перезаписываются (продукт ещё не принимает платежи).

Revision ID: 0019_ruble_prices
Revises: 0018_plans
Create Date: 2026-07-10
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0019_ruble_prices"
down_revision: str | None = "0018_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUBLE_PRICES = {"free": 0, "pro": 99000, "business": 399000}


def upgrade() -> None:
    op.alter_column("plans", "price_monthly_cents", new_column_name="price_monthly_kopeks")
    for slug, kopeks in RUBLE_PRICES.items():
        op.execute(f"UPDATE plans SET price_monthly_kopeks = {kopeks} WHERE slug = '{slug}'")


def downgrade() -> None:
    op.alter_column("plans", "price_monthly_kopeks", new_column_name="price_monthly_cents")
    op.execute("UPDATE plans SET price_monthly_cents = 1200 WHERE slug = 'pro'")
    op.execute("UPDATE plans SET price_monthly_cents = 4500 WHERE slug = 'business'")
