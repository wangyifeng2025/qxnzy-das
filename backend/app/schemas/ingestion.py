from datetime import datetime

from pydantic import BaseModel, Field

from app.ingestion.plan import StructurePlan


class IngestTaskRead(BaseModel):
    id: str
    dataset_code: str
    batch_id: str | None = None
    status: str
    progress: int
    user_prompt: str
    error_code: str | None
    error_message: str | None
    attempts: int
    llm_provider: str | None
    llm_model: str | None
    prompt_version: str | None
    plan_source: str | None = None
    tokens_in: int
    tokens_out: int
    llm_calls: int
    duration_ms: int
    mapping_applied: bool
    has_mapping: bool
    file_name: str | None
    candidate_count: int
    created_at: datetime
    finished_at: datetime | None


class IngestCandidateRead(BaseModel):
    id: str
    task_id: str
    batch_id: str | None
    dataset_code: str
    seq: int
    business_key: str | None
    missing_key: list[str] = []
    source_location: dict[str, object]
    source_text: str | None
    raw_values: dict[str, object]
    values: dict[str, object]
    field_sources: dict[str, object]
    conflicts: list[dict[str, object]]
    errors: list[str]
    warnings: list[str]
    completeness: int
    triage: str
    duplicate_of: str | None
    target_record_id: str | None
    status: str
    record_id: str | None


class CandidateUpdate(BaseModel):
    values: dict[str, object]


class CandidateBulkUpdate(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=500)
    values: dict[str, object]


class CandidateReassess(BaseModel):
    """不传 candidate_ids 时重新校验任务里所有未确认的候选。"""

    candidate_ids: list[str] | None = Field(default=None, max_length=500)


class ReassessResult(BaseModel):
    checked: int
    ready: int
    updated: int


class ReferenceColumn(BaseModel):
    header: str
    field: str | None
    label: str | None = None


class ReferenceSheet(BaseModel):
    name: str
    rows: int
    columns: list[ReferenceColumn]


class ReferenceResult(BaseModel):
    """补传参照表的预览或回填结果。"""

    file_name: str
    sheets: list[ReferenceSheet]
    sheet: str | None
    key: list[str]
    fill: list[str]
    overwrite: bool
    candidates: int
    matched: int
    unmatched: int
    ambiguous: int
    changed: int
    overwritten: int
    unmatched_samples: list[str]
    applied: bool = False
    ready: int = 0


class ConfirmWrite(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=200)
    submit: bool = False


class ConfirmResult(BaseModel):
    created: int
    submitted: int
    updated: int = 0


class MappingWrite(BaseModel):
    mappings: list[dict[str, object]]


class BatchCreate(BaseModel):
    dataset_codes: list[str] = Field(min_length=1, max_length=20)
    title: str = ""


class BatchRead(BaseModel):
    id: str
    title: str
    dataset_codes: list[str]
    status: str
    task_count: int
    candidate_count: int
    auto_count: int
    review_count: int
    missing_count: int
    duplicate_count: int
    created_at: datetime


class PlanRead(BaseModel):
    task_id: str
    status: str
    plan_source: str | None
    profile: dict[str, object] | None
    plan: dict[str, object] | None
    dry_run: dict[str, object] | None


class PlanWrite(BaseModel):
    plan: StructurePlan
    remember: bool = True


class GapRead(BaseModel):
    dataset_code: str
    dataset_name: str
    code: str
    label: str
    count: int
    reason: str = "missing"


class CompleteResult(BaseModel):
    candidate: IngestCandidateRead
    filled: list[str] = Field(default_factory=list)
    message: str = ""


class TemplateRead(BaseModel):
    id: str
    dataset_code: str
    signature: str
    scope: str
    department_id: int | None
    hits: int
    updated_at: datetime


class AliasRead(BaseModel):
    id: str
    dataset_code: str
    header_norm: str
    header_raw: str
    field_code: str
    scope: str
    hits: int
