"""remember when the TLS certificate was last inspected

Срок сертификата снимался на КАЖДОЙ http-проверке: отдельное соединение с
резолвом и полным TLS-хендшейком мимо основного запроса. При интервале в минуту
это около полутора тысяч лишних подключений в сутки на монитор — двойная
нагрузка и на воркер, и на чужой сайт, ради значения, которое меняется раз
в несколько месяцев.

Колонка хранит момент последнего снятия; решение «пора ли» принимает шедулер
при публикации задачи. NULL — ещё ни разу, сертификат снимется на первой же
проверке.

Revision ID: 0024_monitor_ssl_checked_at
Revises: 0023_push_subscription_org_scope
Create Date: 2026-07-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_monitor_ssl_checked_at"
down_revision: str | None = "0023_push_subscription_org_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("monitors", sa.Column("ssl_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("monitors", "ssl_checked_at")
