"""email verification

users.email_verified_at — момент подтверждения email (NULL = не подтверждён).
email_verification_tokens — sha256-hash одноразового токена (TTL, used_at),
таблица не org-scoped, RLS не нужен (как password_reset_tokens).

Revision ID: 0015_email_verification
Revises: 0014_ssl_expiry
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_email_verification"
down_revision: str | None = "0014_ssl_expiry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified_at")
