"""文件解析任务、批次、候选记录、计划模板与别名。确认前不写入填报记录。"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import uuid_hex

TASK_STATUSES = (
    "queued",
    "parsing",
    "awaiting_plan",
    "extracting",
    "pending_confirmation",
    "completed",
    "failed",
    "cancelled",
)
BATCH_STATUSES = ("collecting", "parsing", "reviewing", "completed", "cancelled")
TRIAGE_CODES = ("auto", "review", "missing", "duplicate")


class IngestBatch(Base):
    __tablename__ = "ingest_batch"
    __table_args__ = (
        CheckConstraint(
            "status IN ('collecting', 'parsing', 'reviewing', 'completed', 'cancelled')",
            name="ck_ingest_batch_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    title: Mapped[str] = mapped_column(String(120), default="")
    dataset_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("sys_department.id"))
    status: Mapped[str] = mapped_column(String(20), default="collecting", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestTask(Base):
    __tablename__ = "ingest_task"
    __table_args__ = (
        Index("uq_ingest_task_idempotency", "idempotency_key", unique=True),
        CheckConstraint(
            "status IN ('queued', 'parsing', 'awaiting_plan', 'extracting', "
            "'pending_confirmation', 'completed', 'failed', 'cancelled')",
            name="ck_ingest_task_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    dataset_code: Mapped[str] = mapped_column(String(40), index=True)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingest_batch.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("sys_department.id"))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    user_prompt: Mapped[str] = mapped_column(String(500), default="")
    idempotency_key: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(String(500))
    llm_provider: Mapped[str | None] = mapped_column(String(40))
    llm_model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    mapping_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    # 不使用已记住的结构模板和精确匹配，交给模型重新识别
    fresh_plan: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # initial 新建候选；supplement 只给本批次已有候选补空字段
    mode: Mapped[str] = mapped_column(String(20), default="initial", server_default="initial")
    match_key: Mapped[list[str] | None] = mapped_column(JSONB)
    column_mapping: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    profile: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    plan: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    plan_source: Mapped[str | None] = mapped_column(String(20))
    dry_run: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    usage_breakdown: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestFile(Base):
    __tablename__ = "ingest_file"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_task.id", ondelete="CASCADE"), unique=True, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str] = mapped_column(String(120))
    row_count: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestCandidate(Base):
    __tablename__ = "ingest_candidate"
    __table_args__ = (
        Index("uq_ingest_candidate_seq", "task_id", "seq", unique=True),
        Index("ix_ingest_candidate_batch_key", "batch_id", "dataset_code", "business_key"),
        CheckConstraint(
            "status IN ('pending', 'rejected', 'confirmed')",
            name="ck_ingest_candidate_status",
        ),
        CheckConstraint(
            "triage IN ('auto', 'review', 'missing', 'duplicate')",
            name="ck_ingest_candidate_triage",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_task.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[str | None] = mapped_column(String(32), index=True)
    dataset_code: Mapped[str] = mapped_column(String(40), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    business_key: Mapped[str | None] = mapped_column(String(120))
    source_location: Mapped[dict[str, object]] = mapped_column(JSONB)
    source_text: Mapped[str | None] = mapped_column(Text)
    raw_values: Mapped[dict[str, object]] = mapped_column(JSONB)
    values: Mapped[dict[str, object]] = mapped_column(JSONB)
    field_sources: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    conflicts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    completeness: Mapped[int] = mapped_column(Integer, default=0)
    triage: Mapped[str] = mapped_column(String(20), default="review")
    duplicate_of: Mapped[str | None] = mapped_column(String(32))
    target_record_id: Mapped[str | None] = mapped_column(ForeignKey("biz_record.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    record_id: Mapped[str | None] = mapped_column(ForeignKey("biz_record.id"))


class IngestPlanTemplate(Base):
    __tablename__ = "ingest_plan_template"
    __table_args__ = (
        Index(
            "uq_ingest_plan_template",
            "dataset_code",
            "signature",
            "scope",
            "department_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    dataset_code: Mapped[str] = mapped_column(String(40), index=True)
    signature: Mapped[str] = mapped_column(String(64))
    plan: Mapped[dict[str, object]] = mapped_column(JSONB)
    scope: Mapped[str] = mapped_column(String(20), default="global")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("sys_department.id"))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"))
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestHeaderAlias(Base):
    __tablename__ = "ingest_header_alias"
    __table_args__ = (
        Index(
            "uq_ingest_header_alias",
            "dataset_code",
            "header_norm",
            "scope",
            "department_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    dataset_code: Mapped[str] = mapped_column(String(40), index=True)
    header_norm: Mapped[str] = mapped_column(String(120))
    header_raw: Mapped[str] = mapped_column(String(120), default="")
    field_code: Mapped[str] = mapped_column(String(40))
    scope: Mapped[str] = mapped_column(String(20), default="global")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("sys_department.id"))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"))
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestRound(Base):
    """批次里每处理完一份文件或执行一条动作，留一条轮次报告。"""

    __tablename__ = "ingest_round"
    __table_args__ = (Index("uq_ingest_round_seq", "batch_id", "seq", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_batch.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(20))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("ingest_task.id", ondelete="SET NULL"))
    action_id: Mapped[str | None] = mapped_column(String(32))
    report: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IngestAction(Base):
    """用户一句话解析出的批量动作。先预览，用户确认后才改候选。"""

    __tablename__ = "ingest_action"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'applied', 'rejected', 'expired')",
            name="ck_ingest_action_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_batch.id", ondelete="CASCADE"), index=True
    )
    message: Mapped[str] = mapped_column(String(500))
    action: Mapped[dict[str, object]] = mapped_column(JSONB)
    preview: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_by: Mapped[int] = mapped_column(ForeignKey("sys_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiCallCache(Base):
    __tablename__ = "ai_call_cache"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    call_type: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    output: Mapped[dict[str, object]] = mapped_column(JSONB)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = [
    "BATCH_STATUSES",
    "TASK_STATUSES",
    "TRIAGE_CODES",
    "AiCallCache",
    "IngestAction",
    "IngestBatch",
    "IngestCandidate",
    "IngestFile",
    "IngestHeaderAlias",
    "IngestPlanTemplate",
    "IngestRound",
    "IngestTask",
]
