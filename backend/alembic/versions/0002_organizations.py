"""organizations, org members, org_id in domain tables

Revision ID: 0002_organizations
Revises: 0001_initial
Create Date: 2026-07-08
"""
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0002_organizations"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_TABLES = ("monitors", "config_versions", "telegram_integrations")


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quota_monitors", sa.Integer(), nullable=True),
        sa.Column("quota_members", sa.Integer(), nullable=True),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "org_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "user_id", name="uq_org_member"),
    )

    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    organizations = sa.table(
        "organizations",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    conn.execute(sa.insert(organizations).values(name="My team", slug="default", created_at=now))
    default_org_id = conn.execute(
        sa.select(organizations.c.id).where(organizations.c.slug == "default")
    ).scalar_one()

    users = sa.table("users", sa.column("id", sa.Integer))
    org_members = sa.table(
        "org_members",
        sa.column("org_id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("role", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    user_ids = conn.execute(sa.select(users.c.id).order_by(users.c.id)).scalars().all()
    for index, user_id in enumerate(user_ids):
        conn.execute(
            sa.insert(org_members).values(
                org_id=default_org_id,
                user_id=user_id,
                role="owner" if index == 0 else "member",
                created_at=now,
            )
        )

    # org_id: сначала nullable, затем backfill, затем NOT NULL + FK (batch — ради sqlite)
    for table in ORG_TABLES:
        op.add_column(table, sa.Column("org_id", sa.Integer(), nullable=True))
        conn.execute(
            sa.update(sa.table(table, sa.column("org_id", sa.Integer))).values(org_id=default_org_id)
        )
        with op.batch_alter_table(table) as batch:
            batch.alter_column("org_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_org_id_organizations", "organizations", ["org_id"], ["id"], ondelete="CASCADE"
            )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])

    # группы упразднены в пользу организаций
    op.drop_index("ix_monitors_group_id", table_name="monitors")
    with op.batch_alter_table("monitors") as batch:
        batch.drop_column("group_id")
    op.drop_table("group_members")
    op.drop_table("groups")


def downgrade() -> None:
    raise NotImplementedError("downgrade is not supported for 0002_organizations")
