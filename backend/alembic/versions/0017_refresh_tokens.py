"""refresh tokens

Сессии с ротацией: короткий access-JWT (15 мин) + refresh-токен (30 дней,
скользящий). В БД sha256-hex токена; revoked_at — ротация/логаут/сброс пароля.
Таблица не org-scoped, RLS не нужен.

Revision ID: 0017_refresh_tokens
Revises: 0016_scheduler_heartbeat
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_refresh_tokens"
down_revision: str | None = "0016_scheduler_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
