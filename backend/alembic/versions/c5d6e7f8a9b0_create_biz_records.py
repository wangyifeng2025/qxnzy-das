"""create fill record tables

Revision ID: c5d6e7f8a9b0
Revises: b8c4d1e2f3a0
Create Date: 2026-11-04 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b8c4d1e2f3a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biz_record",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("dataset_code", sa.String(length=40), nullable=False),
        sa.Column("business_key", sa.String(length=120), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("owner_account", sa.String(length=20), nullable=False),
        sa.Column("filler_type", sa.String(length=20), nullable=False),
        sa.Column("filler_account", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_system", sa.String(length=60), nullable=True),
        sa.Column("source_ref", sa.String(length=80), nullable=True),
        sa.Column("batch_id", sa.String(length=40), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("published_version", sa.Integer(), nullable=False),
        sa.Column("ods_id", sa.String(length=32), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["department_id"], ["sys_department.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_biz_record_dataset_code", "biz_record", ["dataset_code"])
    op.create_index("ix_biz_record_status", "biz_record", ["status"])
    op.create_index(
        "uq_biz_record_active_key",
        "biz_record",
        ["dataset_code", "business_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "biz_record_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("record_id", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["sys_user.id"]),
        sa.ForeignKeyConstraint(["record_id"], ["biz_record.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_biz_record_event_record_id", "biz_record_event", ["record_id"])
    op.create_table(
        "biz_record_version",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("record_id", sa.String(length=32), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["published_by"], ["sys_user.id"]),
        sa.ForeignKeyConstraint(["record_id"], ["biz_record.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_biz_record_version_record_id", "biz_record_version", ["record_id"])
    op.create_index(
        "uq_biz_record_version",
        "biz_record_version",
        ["record_id", "version_no"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_biz_record_version", table_name="biz_record_version")
    op.drop_index("ix_biz_record_version_record_id", table_name="biz_record_version")
    op.drop_table("biz_record_version")
    op.drop_index("ix_biz_record_event_record_id", table_name="biz_record_event")
    op.drop_table("biz_record_event")
    op.drop_index("uq_biz_record_active_key", table_name="biz_record")
    op.drop_index("ix_biz_record_status", table_name="biz_record")
    op.drop_index("ix_biz_record_dataset_code", table_name="biz_record")
    op.drop_table("biz_record")
