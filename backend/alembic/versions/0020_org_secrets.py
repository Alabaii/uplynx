"""org secrets for browser scenarios

Секреты browser-сценариев принадлежат организации, а не окружению воркера.
До этого ${NAME} в шагах резолвился из os.environ: в SaaS-режиме арендатор мог
шагом goto на свой домен унести ключи платформы (JWT_SECRET_KEY, DATABASE_URL,
SMTP_PASSWORD) и секреты соседних организаций.

Значение шифруется Fernet-ключом приложения (как bot token в telegram_integrations)
и в API не возвращается никогда — наружу отдаются только имена.

Для PostgreSQL включаем row-level security по org_id (та же формула, что в 0008).
На sqlite — no-op.

Revision ID: 0020_org_secrets
Revises: 0019_ruble_prices
Create Date: 2026-07-26
"""
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_org_secrets"
down_revision: str | None = "0019_ruble_prices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

ORG_MATCH = (
    "org_id = NULLIF(current_setting('app.org_id', true), '')::int "
    "OR NULLIF(current_setting('app.org_id', true), '') IS NULL"
)


def upgrade() -> None:
    op.create_table(
        "org_secrets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("value_secret", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_org_secret_name"),
    )
    op.create_index("ix_org_secrets_org_id", "org_secrets", ["org_id"])

    if op.get_bind().dialect.name != "postgresql":
        logger.info("0020_org_secrets: row-level security skipped, requires PostgreSQL")
        return
    op.execute("ALTER TABLE org_secrets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_secrets FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY org_isolation ON org_secrets USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY org_isolation ON org_secrets")
        op.execute("ALTER TABLE org_secrets NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE org_secrets DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_org_secrets_org_id", table_name="org_secrets")
    op.drop_table("org_secrets")
