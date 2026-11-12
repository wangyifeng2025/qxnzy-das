"""多轮补齐：轮次报告、批量动作，任务区分首轮与补齐

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-05 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "ingest_task",
        sa.Column("mode", sa.String(20), nullable=False, server_default="initial"),
    )
    op.add_column("ingest_task", sa.Column("match_key", JSON, nullable=True))
    op.create_table(
        "ingest_round",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(32),
            sa.ForeignKey("ingest_batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column(
            "task_id",
            sa.String(32),
            sa.ForeignKey("ingest_task.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action_id", sa.String(32), nullable=True),
        sa.Column("report", JSON, nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("sys_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ingest_round_batch_id", "ingest_round", ["batch_id"])
    op.create_index("uq_ingest_round_seq", "ingest_round", ["batch_id", "seq"], unique=True)
    op.create_table(
        "ingest_action",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(32),
            sa.ForeignKey("ingest_batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("action", JSON, nullable=False),
        sa.Column("preview", JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("sys_user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('proposed', 'applied', 'rejected', 'expired')",
            name="ck_ingest_action_status",
        ),
    )
    op.create_index("ix_ingest_action_batch_id", "ingest_action", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_ingest_action_batch_id", table_name="ingest_action")
    op.drop_table("ingest_action")
    op.drop_index("uq_ingest_round_seq", table_name="ingest_round")
    op.drop_index("ix_ingest_round_batch_id", table_name="ingest_round")
    op.drop_table("ingest_round")
    op.drop_column("ingest_task", "match_key")
    op.drop_column("ingest_task", "mode")
