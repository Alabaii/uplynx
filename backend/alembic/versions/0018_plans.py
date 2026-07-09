"""plans and organization plan assignment

Тарифные планы платформы: редактируются суперадмином в админ-панели,
поэтому живут в БД, а не в env. Таблица глобальная (не org-scoped), RLS не нужен;
доступ роли monitor_app приходит через ALTER DEFAULT PRIVILEGES (postgres-init.sh).
Сид — согласованная владельцем сетка Free/Pro/Business; гейтинг лимитов — отдельный этап.

Revision ID: 0018_plans
Revises: 0017_refresh_tokens
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_plans"
down_revision: str | None = "0017_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    plans = op.create_table(
        "plans",
        sa.Column("slug", sa.String(length=40), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("price_monthly_cents", sa.Integer(), nullable=False),
        sa.Column("annual_discount_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_monitors", sa.Integer(), nullable=False),
        sa.Column("min_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("max_browser_monitors", sa.Integer(), nullable=False),
        sa.Column("browser_min_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        # NULL — без лимита участников
        sa.Column("max_members", sa.Integer(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(
        plans,
        [
            {
                "slug": "free",
                "name": "Free",
                "price_monthly_cents": 0,
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
                "price_monthly_cents": 1200,
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
                "price_monthly_cents": 4500,
                "annual_discount_pct": 17,
                "max_monitors": 200,
                "min_interval_seconds": 10,
                "max_browser_monitors": 25,
                "browser_min_interval_seconds": 60,
                "max_members": None,
                "retention_days": 365,
                "sort_order": 2,
            },
        ],
    )
    op.add_column(
        "organizations",
        sa.Column("plan_slug", sa.String(length=40), nullable=False, server_default="free"),
    )
    # sqlite не умеет ALTER с constraint (тесты миграций); на прод-PG ключ обязателен
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_organizations_plan_slug", "organizations", "plans", ["plan_slug"], ["slug"]
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_organizations_plan_slug", "organizations", type_="foreignkey")
    op.drop_column("organizations", "plan_slug")
    op.drop_table("plans")
