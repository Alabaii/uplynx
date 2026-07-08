"""incidents

Инцидент — непрерывный период, когда эффективный статус монитора не "up".
Открывается при переходе up/pending → down/degraded, severity фиксирует худшее
наблюдённое состояние, закрывается при возврате в up.

Для PostgreSQL включаем row-level security по org_id (та же формула, что в 0008):
защита в глубину от забытого WHERE org_id. На sqlite — no-op.

Revision ID: 0010_incidents
Revises: 0009_status_page
Create Date: 2026-07-09
"""
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_incidents"
down_revision: str | None = "0009_status_page"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

ORG_MATCH = (
    "org_id = NULLIF(current_setting('app.org_id', true), '')::int "
    "OR NULLIF(current_setting('app.org_id', true), '') IS NULL"
)


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitor_id", sa.Integer(), sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("trigger_error", sa.Text(), nullable=True),
    )
    op.create_index("ix_incidents_org_id", "incidents", ["org_id"])
    op.create_index("ix_incidents_monitor_id", "incidents", ["monitor_id"])
    op.create_index("ix_incidents_started_at", "incidents", ["started_at"])
    op.create_index("ix_incidents_org_started", "incidents", ["org_id", "started_at"])

    if op.get_bind().dialect.name != "postgresql":
        logger.info("0010_incidents: row-level security skipped, requires PostgreSQL")
        return
    op.execute("ALTER TABLE incidents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE incidents FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY org_isolation ON incidents USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY org_isolation ON incidents")
        op.execute("ALTER TABLE incidents NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE incidents DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_incidents_org_started", table_name="incidents")
    op.drop_index("ix_incidents_started_at", table_name="incidents")
    op.drop_index("ix_incidents_monitor_id", table_name="incidents")
    op.drop_index("ix_incidents_org_id", table_name="incidents")
    op.drop_table("incidents")
