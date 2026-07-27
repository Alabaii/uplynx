"""push subscription is unique per organization, not globally

Таблица push_subscriptions org-scoped и закрыта RLS: запрос с выставленным
app.org_id не видит строки других организаций. Глобальный UNIQUE(endpoint)
с этим не сочетался — участник двух воркспейсов, подписавшийся на уведомления
в обоих, во втором получал IntegrityError (500): существующая строка невидима,
а вставка упирается в констрейнт.

Уникальность переносится на пару (org_id, endpoint). Дубликатов быть не может:
прежний констрейнт был строже, поэтому пересоздание безопасно на живых данных.

Revision ID: 0023_push_subscription_org_scope
Revises: 0022_rate_limit_hits
Create Date: 2026-07-27
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0023_push_subscription_org_scope"
down_revision: str | None = "0022_rate_limit_hits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.drop_constraint("uq_push_subscriptions_endpoint", type_="unique")
        batch.create_unique_constraint("uq_push_subscriptions_org_endpoint", ["org_id", "endpoint"])


def downgrade() -> None:
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.drop_constraint("uq_push_subscriptions_org_endpoint", type_="unique")
        batch.create_unique_constraint("uq_push_subscriptions_endpoint", ["endpoint"])
