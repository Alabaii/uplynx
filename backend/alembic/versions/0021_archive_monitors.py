"""archive monitors and scope slug uniqueness to the organization

Две связанные вещи, потому что обе про одно ограничение уникальности.

1. Удаления монитора не было: DELETE только выключал его, монитор навсегда
   оставался в списке как «на паузе», а слаг — занятым. Теперь есть archived_at:
   монитор исчезает из продукта, история проверок остаётся в БД.

2. Уникальность слага была по (user_id, slug), хотя весь код проверяет пару
   (org_id, slug). Участник двух организаций, создав одинаковый слаг во второй,
   получал IntegrityError → 500 вместо понятного 409.

Новый индекс частичный: archived_at IS NULL. Архивация освобождает слаг,
и его можно занять заново.

Revision ID: 0021_archive_monitors
Revises: 0020_org_secrets
Create Date: 2026-07-27
"""
import logging
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0021_archive_monitors"
down_revision: str | None = "0020_org_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def _archive_slug_duplicates() -> None:
    """Старое ограничение допускало одинаковый слаг у разных участников организации.

    Такие пары ломали бы новый индекс. Оставляем самый ранний монитор, остальные
    архивируем — данные не теряются, но их слаг освобождается.
    """
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT id FROM monitors WHERE id NOT IN ("
            "  SELECT MIN(id) FROM monitors GROUP BY org_id, slug"
            ")"
        )
    ).all()
    if not duplicates:
        return
    ids = [row[0] for row in duplicates]
    logger.warning(
        "0021_archive_monitors: %s монитор(ов) с дублирующимся слагом в организации архивированы: %s",
        len(ids),
        ids,
    )
    bind.execute(
        sa.text("UPDATE monitors SET archived_at = :now, enabled = :off, next_run_at = NULL WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"now": datetime.now(timezone.utc), "off": False, "ids": ids},
    )


def upgrade() -> None:
    op.add_column("monitors", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    _archive_slug_duplicates()
    with op.batch_alter_table("monitors") as batch:
        batch.drop_constraint("uq_monitor_user_slug", type_="unique")
    op.create_index(
        "uq_monitor_org_slug_active",
        "monitors",
        ["org_id", "slug"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_monitor_org_slug_active", table_name="monitors")
    with op.batch_alter_table("monitors") as batch:
        batch.create_unique_constraint("uq_monitor_user_slug", ["user_id", "slug"])
    op.drop_column("monitors", "archived_at")
