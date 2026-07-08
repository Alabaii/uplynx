"""one telegram integration per organization

Revision ID: 0003_telegram_org_unique
Revises: 0002_organizations
Create Date: 2026-07-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_telegram_org_unique"
down_revision: str | None = "0002_organizations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    integrations = sa.table(
        "telegram_integrations",
        sa.column("id", sa.Integer),
        sa.column("org_id", sa.Integer),
    )

    # дедупликация: в каждой организации остаётся строка с максимальным id (последняя настроенная)
    keep_ids = sa.select(sa.func.max(integrations.c.id)).group_by(integrations.c.org_id).scalar_subquery()
    conn.execute(sa.delete(integrations).where(integrations.c.id.not_in(keep_ids)))

    # интеграция становится одной на организацию, а не на пользователя
    op.drop_index("ix_telegram_integrations_org_id", table_name="telegram_integrations")
    with op.batch_alter_table("telegram_integrations") as batch:
        batch.drop_constraint("uq_telegram_user", type_="unique")
    op.create_index("ix_telegram_integrations_org_id", "telegram_integrations", ["org_id"], unique=True)


def downgrade() -> None:
    raise NotImplementedError("downgrade is not supported for 0003_telegram_org_unique")
