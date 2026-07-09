"""ssl expiry

Мониторинг срока действия TLS-сертификата: воркер обновляет ssl_expires_at
на каждой https-проверке, ssl_alerted_days хранит самый острый порог (30/14/7/1),
по которому алерт уже отправлен — защита от повторов на каждой проверке.

Revision ID: 0014_ssl_expiry
Revises: 0013_incident_renotify
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_ssl_expiry"
down_revision: str | None = "0013_incident_renotify"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("monitors", sa.Column("ssl_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("monitors", sa.Column("ssl_alerted_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("monitors", "ssl_alerted_days")
    op.drop_column("monitors", "ssl_expires_at")
