"""row-level security by org_id (postgresql only)

Защита в глубину от забытого WHERE org_id в API-коде, а не от злонамеренного DBA:
приложение подключается владельцем таблиц, поэтому обязателен FORCE ROW LEVEL SECURITY
(владелец без FORCE обходит политики). Семантика политики org_isolation:
- запрос выставил app.org_id (deps.get_current_org_member) — видны только строки этой организации;
- настройка не выставлена (воркеры, scheduler, миграции, psql-админ) — полный доступ,
  их запросы кросс-организационные, это осознанно.

check_results не трогаем: таблица партиционированная, доступ к ней и так через join мониторов.
organizations/org_members/users — глобальные, без org_id-изоляции.

Revision ID: 0008_row_level_security
Revises: 0007_audit_log
Create Date: 2026-07-08
"""
import logging
from collections.abc import Sequence

from alembic import op

revision: str = "0008_row_level_security"
down_revision: str | None = "0007_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

RLS_TABLES = (
    "monitors",
    "config_versions",
    "telegram_integrations",
    "push_subscriptions",
    "uptime_daily",
    "audit_log",
)

ORG_MATCH = (
    "org_id = NULLIF(current_setting('app.org_id', true), '')::int "
    "OR NULLIF(current_setting('app.org_id', true), '') IS NULL"
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        logger.info("0008_row_level_security: skipped, row-level security requires PostgreSQL")
        return
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_isolation ON {table} USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
