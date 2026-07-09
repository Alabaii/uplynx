"""scheduler heartbeat

Единственная строка (id=1) с моментом последнего тика шедулера — для liveness.
Не org-scoped, RLS не нужен.

Revision ID: 0016_scheduler_heartbeat
Revises: 0015_email_verification
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_scheduler_heartbeat"
down_revision: str | None = "0015_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduler_heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scheduler_heartbeat")
