"""incident renotify

Повторные алерты по открытому инциденту: last_notified_at хранит момент
последнего отправленного уведомления. NULL — уведомляли только при открытии
(считаем от started_at).

Revision ID: 0013_incident_renotify
Revises: 0012_password_reset
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_incident_renotify"
down_revision: str | None = "0012_password_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "last_notified_at")
