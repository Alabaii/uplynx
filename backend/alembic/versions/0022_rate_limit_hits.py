"""rate limit counters in the database

Счётчики попыток жили в памяти процесса. Две проблемы:

1. При нескольких репликах API каждая считает свои пять попыток входа —
   защита от перебора слабеет пропорционально их числу, причём молча.
2. Словарь заводил запись на каждый уникальный адрес и никогда её не удалял,
   даже когда окно давно истекло: медленная утечка памяти на публичной
   регистрации.

Таблица не org-scoped (ключ — адрес или пользователь), RLS не нужна.

Revision ID: 0022_rate_limit_hits
Revises: 0021_archive_monitors
Create Date: 2026-07-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_rate_limit_hits"
down_revision: str | None = "0021_archive_monitors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_hits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=320), nullable=False),
        sa.Column("hit_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_limit_hits_scope_key_at", "rate_limit_hits", ["scope", "key", "hit_at"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_hits_scope_key_at", table_name="rate_limit_hits")
    op.drop_table("rate_limit_hits")
