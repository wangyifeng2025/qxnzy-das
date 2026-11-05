"""create ingest tables

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-04 20:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_task",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("dataset_code", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("user_prompt", sa.String(length=500), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("llm_provider", sa.String(length=40), nullable=True),
        sa.Column("llm_model", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("mapping_applied", sa.Boolean(), nullable=False),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["sys_department.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ingest_task_idempotency"),
        sa.CheckConstraint(
            "status IN ('queued', 'parsing', 'extracting', 'pending_confirmation', "
            "'completed', 'failed', 'cancelled')",
            name="ck_ingest_task_status",
        ),
    )
    op.create_index("ix_ingest_task_dataset_code", "ingest_task", ["dataset_code"])
    op.create_index("ix_ingest_task_status", "ingest_task", ["status"])
    op.create_table(
        "ingest_file",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["ingest_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_ingest_file_task"),
    )
    op.create_table(
        "ingest_candidate",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("source_location", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duplicate_of", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("record_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["record_id"], ["biz_record.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["ingest_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "seq", name="uq_ingest_candidate_seq"),
        sa.CheckConstraint(
            "status IN ('pending', 'rejected', 'confirmed')",
            name="ck_ingest_candidate_status",
        ),
    )
    op.create_index("ix_ingest_candidate_task_id", "ingest_candidate", ["task_id"])


def downgrade() -> None:
    op.drop_table("ingest_candidate")
    op.drop_table("ingest_file")
    op.drop_index("ix_ingest_task_status", table_name="ingest_task")
    op.drop_index("ix_ingest_task_dataset_code", table_name="ingest_task")
    op.drop_table("ingest_task")
