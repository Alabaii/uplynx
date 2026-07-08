"""daily uptime aggregates for check results retention

Revision ID: 0004_uptime_daily
Revises: 0003_telegram_org_unique
Create Date: 2026-07-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_uptime_daily"
down_revision: str | None = "0003_telegram_org_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uptime_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitor_id", sa.Integer(), sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("checks_total", sa.Integer(), nullable=False),
        sa.Column("checks_up", sa.Integer(), nullable=False),
        sa.Column("checks_degraded", sa.Integer(), nullable=False),
        sa.Column("checks_down", sa.Integer(), nullable=False),
        sa.Column("avg_response_ms", sa.Integer(), nullable=True),
        sa.UniqueConstraint("monitor_id", "date", name="uq_uptime_daily_monitor_date"),
    )
    op.create_index("ix_uptime_daily_org_id", "uptime_daily", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_uptime_daily_org_id", table_name="uptime_daily")
    op.drop_table("uptime_daily")
