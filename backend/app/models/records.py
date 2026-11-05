from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import uuid_hex


class BizRecord(Base):
    __tablename__ = "biz_record"
    __table_args__ = (
        Index(
            "uq_biz_record_active_key",
            "dataset_code",
            "business_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_dept', 'pending_domain', 'pending_center', "
            "'returned', 'published', 'archived')",
            name="ck_biz_record_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_hex)
    dataset_code: Mapped[str] = mapped_column(String(40), index=True)
    business_key: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("sys_department.id"))
    owner_account: Mapped[str] = mapped_column(String(20), default="")
    filler_type: Mapped[str] = mapped_column(String(20))
    filler_account: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    completeness: Mapped[int] = mapped_column(Integer, default=0)
    field_sources: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    source_type: Mapped[str] = mapped_column(String(20), default="manual")
    source_system: Mapped[str | None] = mapped_column(String(60))
    source_ref: Mapped[str | None] = mapped_column(String(80))
    batch_id: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    published_version: Mapped[int] = mapped_column(Integer, default=0)
    ods_id: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BizRecordEvent(Base):
    __tablename__ = "biz_record_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("biz_record.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(String(500))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"))
    diff: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BizRecordVersion(Base):
    __tablename__ = "biz_record_version"
    __table_args__ = (Index("uq_biz_record_version", "record_id", "version_no", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("biz_record.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    schema_version: Mapped[int] = mapped_column(Integer)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("sys_user.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
