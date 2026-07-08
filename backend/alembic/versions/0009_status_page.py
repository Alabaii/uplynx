"""public status page flag on organizations

Revision ID: 0009_status_page
Revises: 0008_row_level_security
Create Date: 2026-07-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_status_page"
down_revision: str | None = "0008_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # sa.false() рендерится как 0 на sqlite и false на postgres
    op.add_column(
        "organizations",
        sa.Column("status_page_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("status_page_enabled")
