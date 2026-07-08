"""password reset tokens + org alert emails

password_reset_tokens хранит sha256-hash одноразового токена сброса пароля
(TTL 1 час, used_at отмечает использование). Таблица не org-scoped —
RLS не нужен.

organizations.alert_emails — список адресов для email-алертов организации.

Revision ID: 0012_password_reset
Revises: 0011_maintenance_windows
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_password_reset"
down_revision: str | None = "0011_maintenance_windows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.add_column(
        "organizations",
        sa.Column("alert_emails", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("alert_emails")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
