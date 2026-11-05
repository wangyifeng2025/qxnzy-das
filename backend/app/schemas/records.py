from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DatasetAccess(BaseModel):
    code: str
    name: str
    category: str
    can_fill: bool
    can_review: bool


class FieldMeta(BaseModel):
    code: str
    label: str
    kind: str
    group: str
    required: bool
    max_length: int | None = None
    dict_code: str | None = None
    visible_when: str | None = None
    sensitive: bool = False
    default: str | None = None


class DictOption(BaseModel):
    value: str
    label: str


class GroupMeta(BaseModel):
    title: str
    hint: str | None = None


class DatasetMeta(BaseModel):
    code: str
    name: str
    list_fields: list[str]
    business_key_fields: list[str] = []
    can_fill: bool
    can_review: bool = False
    can_export_sensitive: bool
    owner_field: str | None
    owner_name_field: str | None
    department_field: str
    filler_type: str | None
    account: str
    user_name: str
    department_name: str | None
    departments: list[str]
    dicts: dict[str, list[DictOption]]
    title_ranks: list[str]
    groups: list[GroupMeta]
    fields: list[FieldMeta]


class RecordWrite(BaseModel):
    payload: dict[str, object]


class ImportRow(BaseModel):
    row: int
    ok: bool
    errors: list[str]
    payload: dict[str, object]


class ImportCommit(BaseModel):
    payloads: list[dict[str, object]] = Field(max_length=500)
    submit: bool = False


class ImportResult(BaseModel):
    created: int
    submitted: int


class BatchAction(BaseModel):
    action: Literal["submit", "withdraw", "approve", "return"]
    ids: list[str] = Field(min_length=1, max_length=200)
    comment: str = Field(default="", max_length=500)


class BatchFailure(BaseModel):
    id: str
    reason: str


class BatchResult(BaseModel):
    done: int
    failed: list[BatchFailure]


class ReviewWrite(BaseModel):
    decision: Literal["approve", "return"]
    comment: str = ""


class CommentWrite(BaseModel):
    comment: str = Field(min_length=1, max_length=500)


class RecordListItem(BaseModel):
    id: str
    dataset_code: str
    dataset_name: str
    business_key: str
    status: str
    owner_account: str
    filler_account: str
    filler_type: str
    department_name: str | None
    summary: dict[str, object]
    warnings: list[str]
    errors: list[str] = Field(default_factory=list)
    completeness: int = 0
    updated_at: datetime
    published_version: int
    can_review: bool = False
    can_revise: bool = False


class RecordDetail(RecordListItem):
    payload: dict[str, object]
    field_sources: dict[str, object] = Field(default_factory=dict)
    source_type: str = "manual"
    schema_version: int
    ods_id: str | None


class RecordEventRead(BaseModel):
    id: int
    action: str
    from_status: str | None
    to_status: str
    comment: str | None
    actor_account: str | None
    diff: dict[str, object] | None
    created_at: datetime


class RecordVersionRead(BaseModel):
    version_no: int
    payload: dict[str, object]
    published_at: datetime
