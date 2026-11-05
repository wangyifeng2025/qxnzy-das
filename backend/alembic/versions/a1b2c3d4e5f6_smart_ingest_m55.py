"""智能填报增强 M5.5：批次、结构计划、模板记忆、别名、AI 调用缓存。

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    _batch()
    _task()
    _candidate()
    _record()
    _template()
    _alias()
    _cache()


def _batch() -> None:
    op.create_table(
        "ingest_batch",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False, server_default=""),
        sa.Column("dataset_codes", JSON, nullable=False, server_default="[]"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("sys_user.id"), nullable=False),
        sa.Column(
            "department_id",
            sa.Integer(),
            sa.ForeignKey("sys_department.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="collecting"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('collecting', 'parsing', 'reviewing', 'completed', 'cancelled')",
            name="ck_ingest_batch_status",
        ),
    )
    op.create_index("ix_ingest_batch_status", "ingest_batch", ["status"])


def _task() -> None:
    op.add_column(
        "ingest_task",
        sa.Column("batch_id", sa.String(32), sa.ForeignKey("ingest_batch.id", ondelete="SET NULL")),
    )
    op.create_index("ix_ingest_task_batch_id", "ingest_task", ["batch_id"])
    op.add_column("ingest_task", sa.Column("profile", JSON))
    op.add_column("ingest_task", sa.Column("plan", JSON))
    op.add_column("ingest_task", sa.Column("plan_source", sa.String(20)))
    op.add_column("ingest_task", sa.Column("dry_run", JSON))
    op.add_column("ingest_task", sa.Column("usage_breakdown", JSON))
    op.drop_constraint("ck_ingest_task_status", "ingest_task", type_="check")
    op.create_check_constraint(
        "ck_ingest_task_status",
        "ingest_task",
        "status IN ('queued', 'parsing', 'awaiting_plan', 'extracting', "
        "'pending_confirmation', 'completed', 'failed', 'cancelled')",
    )


def _candidate() -> None:
    op.add_column("ingest_candidate", sa.Column("batch_id", sa.String(32)))
    op.create_index("ix_ingest_candidate_batch_id", "ingest_candidate", ["batch_id"])
    op.add_column("ingest_candidate", sa.Column("dataset_code", sa.String(40)))
    op.add_column("ingest_candidate", sa.Column("business_key", sa.String(120)))
    op.add_column("ingest_candidate", sa.Column("source_text", sa.Text()))
    op.add_column(
        "ingest_candidate",
        sa.Column("field_sources", JSON, nullable=True, server_default="{}"),
    )
    op.add_column(
        "ingest_candidate", sa.Column("conflicts", JSON, nullable=True, server_default="[]")
    )
    op.add_column(
        "ingest_candidate",
        sa.Column("completeness", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingest_candidate",
        sa.Column("triage", sa.String(20), nullable=False, server_default="review"),
    )
    op.add_column(
        "ingest_candidate",
        sa.Column("target_record_id", sa.String(32), sa.ForeignKey("biz_record.id")),
    )
    op.execute(
        "UPDATE ingest_candidate AS c SET dataset_code = t.dataset_code "
        "FROM ingest_task AS t WHERE t.id = c.task_id"
    )
    op.alter_column("ingest_candidate", "dataset_code", nullable=False)
    op.create_index(
        "ix_ingest_candidate_batch_key",
        "ingest_candidate",
        ["batch_id", "dataset_code", "business_key"],
    )
    op.drop_constraint("ck_ingest_candidate_status", "ingest_candidate", type_="check")
    op.create_check_constraint(
        "ck_ingest_candidate_status",
        "ingest_candidate",
        "status IN ('pending', 'rejected', 'confirmed')",
    )
    op.create_check_constraint(
        "ck_ingest_candidate_triage",
        "ingest_candidate",
        "triage IN ('auto', 'review', 'missing', 'duplicate')",
    )


def _record() -> None:
    op.add_column("biz_record", sa.Column("errors", JSON, nullable=True, server_default="[]"))
    op.add_column(
        "biz_record",
        sa.Column("completeness", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "biz_record", sa.Column("field_sources", JSON, nullable=True, server_default="{}")
    )


def _template() -> None:
    op.create_table(
        "ingest_plan_template",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("dataset_code", sa.String(40), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("plan", JSON, nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="global"),
        sa.Column(
            "department_id",
            sa.Integer(),
            sa.ForeignKey("sys_department.id"),
            nullable=True,
        ),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("sys_user.id"), nullable=True),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_ingest_plan_template",
        "ingest_plan_template",
        ["dataset_code", "signature", "scope", "department_id"],
        unique=True,
    )
    op.create_index(
        "ix_ingest_plan_template_dataset_code",
        "ingest_plan_template",
        ["dataset_code"],
    )


def _alias() -> None:
    op.create_table(
        "ingest_header_alias",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("dataset_code", sa.String(40), nullable=False),
        sa.Column("header_norm", sa.String(120), nullable=False),
        sa.Column("header_raw", sa.String(120), nullable=False, server_default=""),
        sa.Column("field_code", sa.String(40), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="global"),
        sa.Column(
            "department_id",
            sa.Integer(),
            sa.ForeignKey("sys_department.id"),
            nullable=True,
        ),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("sys_user.id"), nullable=True),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_ingest_header_alias",
        "ingest_header_alias",
        ["dataset_code", "header_norm", "scope", "department_id"],
        unique=True,
    )
    op.create_index("ix_ingest_header_alias_dataset_code", "ingest_header_alias", ["dataset_code"])


def _cache() -> None:
    op.create_table(
        "ai_call_cache",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("call_type", sa.String(40), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("output", JSON, nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_call_cache_cache_key", "ai_call_cache", ["cache_key"], unique=True)


def downgrade() -> None:
    op.drop_table("ai_call_cache")
    op.drop_table("ingest_header_alias")
    op.drop_table("ingest_plan_template")
    op.drop_column("biz_record", "field_sources")
    op.drop_column("biz_record", "completeness")
    op.drop_column("biz_record", "errors")
    op.drop_constraint("ck_ingest_candidate_triage", "ingest_candidate", type_="check")
    op.drop_index("ix_ingest_candidate_batch_key", table_name="ingest_candidate")
    op.drop_column("ingest_candidate", "target_record_id")
    op.drop_column("ingest_candidate", "triage")
    op.drop_column("ingest_candidate", "completeness")
    op.drop_column("ingest_candidate", "conflicts")
    op.drop_column("ingest_candidate", "field_sources")
    op.drop_column("ingest_candidate", "source_text")
    op.drop_column("ingest_candidate", "business_key")
    op.drop_column("ingest_candidate", "dataset_code")
    op.drop_index("ix_ingest_candidate_batch_id", table_name="ingest_candidate")
    op.drop_column("ingest_candidate", "batch_id")
    op.drop_constraint("ck_ingest_task_status", "ingest_task", type_="check")
    op.create_check_constraint(
        "ck_ingest_task_status",
        "ingest_task",
        "status IN ('queued', 'parsing', 'extracting', 'pending_confirmation', "
        "'completed', 'failed', 'cancelled')",
    )
    for column in ("usage_breakdown", "dry_run", "plan_source", "plan", "profile"):
        op.drop_column("ingest_task", column)
    op.drop_index("ix_ingest_task_batch_id", table_name="ingest_task")
    op.drop_column("ingest_task", "batch_id")
    op.drop_index("ix_ingest_batch_status", table_name="ingest_batch")
    op.drop_table("ingest_batch")
