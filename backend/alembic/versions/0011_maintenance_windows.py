"""maintenance windows

Окно обслуживания — интервал [starts_at, ends_at) для монитора (monitor_id)
или всей организации (monitor_id IS NULL). Пока окно активно, планировщик
не публикует проверки затронутых мониторов: нет результатов — нет алертов,
инцидентов и порчи uptime.

Для PostgreSQL включаем row-level security по org_id (та же формула, что в 0008):
защита в глубину от забытого WHERE org_id. На sqlite — no-op.

Revision ID: 0011_maintenance_windows
Revises: 0010_incidents
Create Date: 2026-07-09
"""
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_maintenance_windows"
down_revision: str | None = "0010_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

ORG_MATCH = (
    "org_id = NULLIF(current_setting('app.org_id', true), '')::int "
    "OR NULLIF(current_setting('app.org_id', true), '') IS NULL"
)


def upgrade() -> None:
    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitor_id", sa.Integer(), sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_maintenance_windows_org_id", "maintenance_windows", ["org_id"])
    op.create_index("ix_maintenance_windows_org_ends", "maintenance_windows", ["org_id", "ends_at"])

    if op.get_bind().dialect.name != "postgresql":
        logger.info("0011_maintenance_windows: row-level security skipped, requires PostgreSQL")
        return
    op.execute("ALTER TABLE maintenance_windows ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE maintenance_windows FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY org_isolation ON maintenance_windows USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY org_isolation ON maintenance_windows")
        op.execute("ALTER TABLE maintenance_windows NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE maintenance_windows DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_maintenance_windows_org_ends", table_name="maintenance_windows")
    op.drop_index("ix_maintenance_windows_org_id", table_name="maintenance_windows")
    op.drop_table("maintenance_windows")
