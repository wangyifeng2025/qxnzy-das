"""上传文件、查看候选、确认后才生成草稿。批次可容纳多份文件与多个数据表。"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select, update

from app.ai.calls import Caller
from app.ai.client import HttpxLLMClient
from app.ai.extract import complete_fields
from app.ai.schema import completion_input
from app.api.deps import DbSession, require_permissions
from app.core.config import resolved_ai, settings
from app.datasets.access import can_fill, is_center
from app.datasets.registry import get_dataset
from app.datasets.spec import DatasetSpec
from app.ingestion.dedupe import KeyIndex
from app.ingestion.enrich import LookupCache
from app.ingestion.file_check import FileRejected, check_upload, rejection
from app.ingestion.grounding import ground
from app.ingestion.normalize import cell_text
from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.parsers.spreadsheet import parse_csv, parse_xls, parse_xlsx
from app.ingestion.pipeline import assess
from app.ingestion.plan import ColumnMap, SheetPlan, StructurePlan
from app.ingestion.planning import PlanInvalid, validate_plan
from app.ingestion.profile import DocumentProfile
from app.ingestion.queue import enqueue_ingest
from app.ingestion.reference import RefSheet, compare, read_sheets, suggest_key
from app.ingestion.storage import delete_upload, file_digest, save_upload
from app.ingestion.templates import learn_aliases, save_template
from app.ingestion.triage import missing_required
from app.models.common import uuid_hex
from app.models.ingestion import (
    IngestBatch,
    IngestCandidate,
    IngestFile,
    IngestHeaderAlias,
    IngestPlanTemplate,
    IngestTask,
)
from app.models.records import BizRecord
from app.models.system import User
from app.schemas.ingestion import (
    AliasRead,
    BatchCreate,
    BatchRead,
    CandidateBulkUpdate,
    CandidateReassess,
    CandidateUpdate,
    CompleteResult,
    ConfirmResult,
    ConfirmWrite,
    GapRead,
    IngestCandidateRead,
    IngestTaskRead,
    MappingWrite,
    PlanRead,
    PlanWrite,
    ReassessResult,
    ReferenceColumn,
    ReferenceResult,
    ReferenceSheet,
    TemplateRead,
)
from app.services.records import create_record, submit_record, update_record
from app.services.staff import active_department_names, load_dict_options

router = APIRouter(tags=["文件解析"])
Parser = Annotated[User, Depends(require_permissions("ai-parse:use"))]


def _now() -> datetime:
    return datetime.now(UTC)


async def _task_for(session: DbSession, user: User, task_id: str) -> IngestTask:
    task = await session.get(IngestTask, task_id)
    if task is None or (task.created_by != user.id and not is_center(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


async def _batch_for(session: DbSession, user: User, batch_id: str) -> IngestBatch:
    batch = await session.get(IngestBatch, batch_id)
    if batch is None or (batch.created_by != user.id and not is_center(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="批次不存在")
    return batch


async def _read(session: DbSession, task: IngestTask) -> IngestTaskRead:
    filename = await session.scalar(
        select(IngestFile.original_name).where(IngestFile.task_id == task.id)
    )
    count = await session.scalar(
        select(func.count()).select_from(IngestCandidate).where(IngestCandidate.task_id == task.id)
    )
    return IngestTaskRead(
        id=task.id,
        dataset_code=task.dataset_code,
        batch_id=task.batch_id,
        status=task.status,
        progress=task.progress,
        user_prompt=task.user_prompt,
        error_code=task.error_code,
        error_message=task.error_message,
        attempts=task.attempts,
        llm_provider=task.llm_provider,
        llm_model=task.llm_model,
        prompt_version=task.prompt_version,
        plan_source=task.plan_source,
        tokens_in=task.tokens_in,
        tokens_out=task.tokens_out,
        llm_calls=task.llm_calls,
        duration_ms=task.duration_ms,
        mapping_applied=task.mapping_applied,
        has_mapping=task.plan is not None or task.column_mapping is not None,
        file_name=filename if isinstance(filename, str) else None,
        candidate_count=int(count or 0),
        created_at=task.created_at,
        finished_at=task.finished_at,
    )


def _missing_key(spec: DatasetSpec, values: dict[str, object]) -> list[str]:
    """业务主键里为空的字段。为空时不能写入，否则只报“业务主键不能为空”看不出缺哪列。"""
    return [code for code in spec.business_key_fields if not cell_text(values.get(code))]


def _ready_to_confirm(spec: DatasetSpec, row: IngestCandidate) -> bool:
    return not (
        row.errors
        or row.duplicate_of
        or "无权填写" in (row.warnings or [])
        or _missing_key(spec, row.values or {})
    )


def _candidate(row: IngestCandidate) -> IngestCandidateRead:
    return IngestCandidateRead(
        id=row.id,
        task_id=row.task_id,
        batch_id=row.batch_id,
        dataset_code=row.dataset_code,
        seq=row.seq,
        business_key=row.business_key,
        missing_key=_missing_key(get_dataset(row.dataset_code), row.values or {}),
        source_location=row.source_location,
        source_text=row.source_text,
        raw_values=row.raw_values,
        values=row.values,
        field_sources=row.field_sources or {},
        conflicts=list(row.conflicts or []),
        errors=list(row.errors or []),
        warnings=list(row.warnings or []),
        completeness=row.completeness,
        triage=row.triage,
        duplicate_of=row.duplicate_of,
        target_record_id=row.target_record_id,
        status=row.status,
        record_id=row.record_id,
    )


async def _create_task(
    session: DbSession,
    user: User,
    dataset_code: str,
    upload: UploadFile,
    prompt: str,
    batch_id: str | None = None,
    *,
    fresh_plan: bool = False,
) -> IngestTask:
    spec = get_dataset(dataset_code)
    if not can_fill(user, spec):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权为该数据表解析文件")
    if len(prompt) > 500:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="补充提示词不能超过 500 字")
    content = await upload.read()
    try:
        _suffix, mime = check_upload(upload.filename or "", upload.content_type, content)
    except FileRejected as exc:
        raise rejection(exc) from exc
    digest = file_digest(content)
    key = hashlib.sha256(
        f"{user.id}|{spec.code}|{digest}|{prompt.strip()}|{batch_id or ''}"
        f"{'|fresh' if fresh_plan else ''}".encode()
    ).hexdigest()
    existing = await session.scalar(select(IngestTask).where(IngestTask.idempotency_key == key))
    if existing is not None:
        return existing
    task = IngestTask(
        id=uuid_hex(),
        dataset_code=spec.code,
        batch_id=batch_id,
        created_by=user.id,
        department_id=user.department_id,
        status="queued",
        progress=0,
        user_prompt=prompt.strip(),
        idempotency_key=key,
        attempts=0,
        schema_version=spec.schema_version,
        tokens_in=0,
        tokens_out=0,
        llm_calls=0,
        duration_ms=0,
        cancel_requested=False,
        mapping_applied=False,
        fresh_plan=fresh_plan,
        created_at=_now(),
    )
    session.add(task)
    await session.flush()
    session.add(
        IngestFile(
            task_id=task.id,
            original_name=(upload.filename or "upload")[:255],
            stored_path=save_upload(task.id, upload.filename or "upload", content),
            sha256=digest,
            size=len(content),
            mime=mime,
            expires_at=_now() + timedelta(days=settings.ingest_file_retention_days),
        )
    )
    if batch_id:
        batch = await session.get(IngestBatch, batch_id)
        if batch is not None:
            batch.status = "parsing"
            batch.updated_at = _now()
    await session.commit()
    await enqueue_ingest(task.id)
    return task


@router.post(
    "/api/ingestion/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestTaskRead,
)
async def create_task(
    session: DbSession,
    user: Parser,
    dataset_code: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    prompt: Annotated[str, Form()] = "",
    fresh_plan: Annotated[bool, Form()] = False,
) -> IngestTaskRead:
    task = await _create_task(session, user, dataset_code, file, prompt, fresh_plan=fresh_plan)
    return await _read(session, task)


@router.get("/api/ingestion/tasks", response_model=list[IngestTaskRead])
async def list_tasks(session: DbSession, user: Parser) -> list[IngestTaskRead]:
    query = select(IngestTask).order_by(IngestTask.created_at.desc()).limit(50)
    if not is_center(user):
        query = query.where(IngestTask.created_by == user.id)
    rows = (await session.scalars(query)).all()
    return [await _read(session, row) for row in rows]


@router.get("/api/ingestion/tasks/{task_id}", response_model=IngestTaskRead)
async def read_task(task_id: str, session: DbSession, user: Parser) -> IngestTaskRead:
    return await _read(session, await _task_for(session, user, task_id))


@router.post("/api/ingestion/tasks/{task_id}/retry", response_model=IngestTaskRead)
async def retry_task(task_id: str, session: DbSession, user: Parser) -> IngestTaskRead:
    task = await _task_for(session, user, task_id)
    if task.status not in {"failed", "queued"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前状态不能重试")
    task.status = "queued"
    task.error_code = None
    task.error_message = None
    task.cancel_requested = False
    task.progress = 0
    await session.commit()
    await enqueue_ingest(task.id)
    return await _read(session, task)


@router.post("/api/ingestion/tasks/{task_id}/replan", response_model=IngestTaskRead)
async def replan_task(task_id: str, session: DbSession, user: Parser) -> IngestTaskRead:
    """丢弃当前结构和未确认的候选，不用模板，交给模型重新识别结构。"""
    task = await _task_for(session, user, task_id)
    if task.status not in {"awaiting_plan", "pending_confirmation", "failed"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前状态不能重新识别结构")
    written = await session.scalar(
        select(func.count())
        .select_from(IngestCandidate)
        .where(IngestCandidate.task_id == task.id, IngestCandidate.record_id.is_not(None))
    )
    if written:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="已有候选生成草稿，请删除任务后重新上传",
        )
    task.fresh_plan = True
    task.plan = None
    task.plan_source = None
    task.column_mapping = None
    task.mapping_applied = False
    task.dry_run = None
    task.status = "queued"
    task.progress = 0
    task.error_code = None
    task.error_message = None
    task.cancel_requested = False
    await session.commit()
    await enqueue_ingest(task.id)
    return await _read(session, task)


@router.post("/api/ingestion/tasks/{task_id}/cancel", response_model=IngestTaskRead)
async def cancel_task(task_id: str, session: DbSession, user: Parser) -> IngestTaskRead:
    task = await _task_for(session, user, task_id)
    task.cancel_requested = True
    if task.status in {"queued", "failed", "awaiting_plan"}:
        task.status = "cancelled"
        task.finished_at = _now()
    await session.commit()
    return await _read(session, task)


@router.get("/api/ingestion/tasks/{task_id}/plan", response_model=PlanRead)
async def read_plan(task_id: str, session: DbSession, user: Parser) -> PlanRead:
    task = await _task_for(session, user, task_id)
    return PlanRead(
        task_id=task.id,
        status=task.status,
        plan_source=task.plan_source,
        profile=task.profile,
        plan=task.plan,
        dry_run=task.dry_run,
    )


@router.put("/api/ingestion/tasks/{task_id}/plan", response_model=IngestTaskRead)
async def update_plan(
    task_id: str, body: PlanWrite, session: DbSession, user: Parser
) -> IngestTaskRead:
    task = await _task_for(session, user, task_id)
    if task.created_by != user.id and not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能调整自己的任务")
    if task.profile is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="任务尚未完成文件画像")
    profile = DocumentProfile.model_validate(task.profile)
    specs = await _specs_for_task(session, task)
    plan = body.plan.model_copy(update={"source": "user", "confidence": 1})
    try:
        plan = validate_plan(plan, profile, specs)
    except PlanInvalid as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="；".join(exc.errors[:5])) from exc
    task.plan = plan.model_dump(mode="json")
    task.plan_source = "user"
    task.mapping_applied = True
    task.status = "queued"
    task.progress = 0
    if body.remember:
        await save_template(
            session,
            plan,
            profile,
            user,
            task.department_id,
            global_scope=settings.ingest_template_global_scope,
        )
    for code, spec in specs.items():
        if any(sheet.dataset_code == code for sheet in plan.sheets):
            await learn_aliases(session, spec, plan, user, task.department_id)
    await session.commit()
    await enqueue_ingest(task.id)
    return await _read(session, task)


@router.get("/api/ingestion/tasks/{task_id}/mapping")
async def read_mapping(task_id: str, session: DbSession, user: Parser) -> dict[str, object]:
    task = await _task_for(session, user, task_id)
    if task.column_mapping is not None:
        return task.column_mapping
    if task.plan:
        plan = StructurePlan.model_validate(task.plan)
        return {
            "mappings": [
                {
                    "header": column.header,
                    "headers": column.headers,
                    "field": column.field,
                    "fields": column.fields,
                    "transform": column.transform,
                    "group": column.group,
                }
                for sheet in plan.sheets
                for column in sheet.columns
            ]
        }
    return {"mappings": []}


@router.put("/api/ingestion/tasks/{task_id}/mapping", response_model=IngestTaskRead)
async def update_mapping(
    task_id: str, body: MappingWrite, session: DbSession, user: Parser
) -> IngestTaskRead:
    task = await _task_for(session, user, task_id)
    if task.created_by != user.id and not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能调整自己的任务")
    profile = DocumentProfile.model_validate(task.profile or {"kind": "text", "sheets": []})
    sheets = [sheet for sheet in profile.sheets if not sheet.skip_reason]
    if not sheets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="没有可映射的工作表")
    first = sheets[0]
    columns = [ColumnMap.model_validate(item) for item in body.mappings]
    plan = StructurePlan(
        sheets=[
            SheetPlan(
                sheet=first.sheet,
                dataset_code=task.dataset_code,
                header_rows=first.header_rows or [1],
                data_start=max(first.header_rows or [1]) + 1,
                columns=columns,
            )
        ],
        source="user",
        confidence=1,
    )
    task.column_mapping = {"mappings": [column.model_dump() for column in columns]}
    task.plan = plan.model_dump(mode="json")
    task.plan_source = "user"
    task.mapping_applied = True
    task.status = "queued"
    task.progress = 0
    await session.commit()
    await enqueue_ingest(task.id)
    return await _read(session, task)


async def _specs_for_task(session: DbSession, task: IngestTask) -> dict[str, DatasetSpec]:
    codes = [task.dataset_code]
    if task.batch_id:
        batch = await session.get(IngestBatch, task.batch_id)
        if batch is not None:
            codes = [*list(batch.dataset_codes or []), task.dataset_code]
    return {code: get_dataset(code) for code in dict.fromkeys(codes)}


@router.get(
    "/api/ingestion/tasks/{task_id}/candidates",
    response_model=list[IngestCandidateRead],
)
async def list_candidates(
    task_id: str, session: DbSession, user: Parser
) -> list[IngestCandidateRead]:
    await _task_for(session, user, task_id)
    rows = (
        await session.scalars(
            select(IngestCandidate)
            .where(IngestCandidate.task_id == task_id)
            .order_by(IngestCandidate.seq)
        )
    ).all()
    return [_candidate(row) for row in rows]


async def _load_context(
    session: DbSession,
) -> tuple[dict[str, dict[str, str]], dict[str, set[str]], set[str]]:
    found, option_sets = await load_dict_options(session)
    lookups: dict[str, dict[str, str]] = {}
    for code, items in found.items():
        lookups[code] = {item.label: item.value for item in items}
        lookups[code].update({item.value: item.value for item in items})
    names = set(await active_department_names(session))
    return lookups, option_sets, names


@dataclass
class _Context:
    """批量重新校验时共用的字典、查重索引和查库缓存。"""

    lookups: dict[str, dict[str, str]]
    option_sets: dict[str, set[str]]
    names: set[str]
    index: KeyIndex
    cache: LookupCache


async def _context(session: DbSession, dataset_codes: set[str]) -> _Context:
    lookups, option_sets, names = await _load_context(session)
    index = KeyIndex()
    await index.load(session, dataset_codes)
    return _Context(lookups, option_sets, names, index, LookupCache())


async def _reassess(
    session: DbSession,
    row: IngestCandidate,
    values: dict[str, object],
    *,
    source: dict[str, object] | None = None,
    ctx: _Context | None = None,
) -> IngestCandidate:
    task = await session.get(IngestTask, row.task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="任务不存在")
    owner = await session.get(User, task.created_by)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="任务发起人不存在")
    spec = get_dataset(row.dataset_code or task.dataset_code)
    if ctx is None:
        ctx = await _context(session, {spec.code})
    previous = row.values or {}
    sources: dict[str, dict[str, object]] = {}
    for code, item in (row.field_sources or {}).items():
        if isinstance(item, dict) and cell_text(values.get(code)):
            sources[code] = item
    for code, value in values.items():
        if cell_text(value) != cell_text(previous.get(code)) and cell_text(value):
            sources[code] = dict(source or {"source": "user", "score": 1.0})
    verdict = await assess(
        session,
        task,
        spec,
        owner,
        values,
        ctx.lookups,
        ctx.option_sets,
        ctx.names,
        None,
        ctx.index,
        ctx.cache,
        field_sources=sources,
    )
    row.raw_values = values
    row.values = verdict.values
    row.field_sources = verdict.field_sources
    row.conflicts = verdict.conflicts
    row.errors = verdict.errors
    row.warnings = verdict.warnings
    row.completeness = verdict.completeness
    row.triage = verdict.triage
    row.duplicate_of = verdict.duplicate_of
    row.target_record_id = verdict.target_record_id
    row.business_key = verdict.business_key
    return row


@router.patch("/api/ingestion/candidates/{candidate_id}", response_model=IngestCandidateRead)
async def update_candidate(
    candidate_id: str, body: CandidateUpdate, session: DbSession, user: Parser
) -> IngestCandidateRead:
    row = await session.get(IngestCandidate, candidate_id)
    if row is None or row.record_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="候选不存在或已确认")
    await _task_for(session, user, row.task_id)
    await _reassess(session, row, body.values)
    await session.commit()
    return _candidate(row)


@router.post("/api/ingestion/candidates/bulk", response_model=list[IngestCandidateRead])
async def bulk_update_candidates(
    body: CandidateBulkUpdate, session: DbSession, user: Parser
) -> list[IngestCandidateRead]:
    rows = (
        await session.scalars(
            select(IngestCandidate).where(IngestCandidate.id.in_(body.candidate_ids))
        )
    ).all()
    if len(rows) != len(set(body.candidate_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="候选不存在")
    updated: list[IngestCandidate] = []
    ctx = await _context(session, {row.dataset_code for row in rows})
    allowed: set[str] = set()
    for row in rows:
        if row.record_id is not None:
            continue
        if row.task_id not in allowed:
            await _task_for(session, user, row.task_id)
            allowed.add(row.task_id)
        values = {**(row.values or {}), **body.values}
        updated.append(await _reassess(session, row, values, ctx=ctx))
    await session.commit()
    return [_candidate(row) for row in updated]


@router.post(
    "/api/ingestion/tasks/{task_id}/reassess",
    response_model=ReassessResult,
    summary="按当前已发布数据重新校验候选",
)
async def reassess_candidates(
    task_id: str,
    session: DbSession,
    user: Parser,
    body: CandidateReassess | None = None,
) -> ReassessResult:
    """重新查库补全并校验，用于专业库等来源在解析之后才发布数据的情况。"""
    task = await _task_for(session, user, task_id)
    query = select(IngestCandidate).where(
        IngestCandidate.task_id == task_id, IngestCandidate.record_id.is_(None)
    )
    if body is not None and body.candidate_ids:
        query = query.where(IngestCandidate.id.in_(body.candidate_ids))
    rows = (await session.scalars(query.order_by(IngestCandidate.seq))).all()
    if not rows:
        return ReassessResult(checked=0, ready=0, updated=0)
    ctx = await _context(session, {row.dataset_code or task.dataset_code for row in rows})
    specs = {
        row.dataset_code or task.dataset_code: get_dataset(row.dataset_code or task.dataset_code)
        for row in rows
    }
    updated = 0
    for row in rows:
        before = (dict(row.values or {}), list(row.warnings or []), row.triage)
        await _reassess(session, row, dict(row.values or {}), ctx=ctx)
        if before != (dict(row.values or {}), list(row.warnings or []), row.triage):
            updated += 1
    await session.commit()
    ready = sum(
        1 for row in rows if _ready_to_confirm(specs[row.dataset_code or task.dataset_code], row)
    )
    return ReassessResult(checked=len(rows), ready=ready, updated=updated)


def _reference_document(filename: str, content_type: str | None, content: bytes) -> ParsedDocument:
    try:
        suffix, _mime = check_upload(filename, content_type, content)
    except FileRejected as exc:
        raise rejection(exc) from exc
    parsers = {".xlsx": parse_xlsx, ".xls": parse_xls, ".csv": parse_csv}
    parser = parsers.get(suffix)
    if parser is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="参照表只接受 xlsx、xls、csv")
    try:
        document = parser(content)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="参照表无法读取") from exc
    if document.filled_cells > settings.ingest_max_cells:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="参照表数据量过大，请只保留需要的列"
        )
    return document


def _codes(text: str, sheet: RefSheet | None) -> list[str]:
    known = set(sheet.fields) if sheet else set()
    return [
        code for code in dict.fromkeys(item.strip() for item in text.split(",")) if code in known
    ]


@router.post("/api/ingestion/tasks/{task_id}/reference", response_model=ReferenceResult)
async def apply_reference(
    task_id: str,
    session: DbSession,
    user: Parser,
    file: Annotated[UploadFile, File()],
    sheet: Annotated[str, Form()] = "",
    key: Annotated[str, Form()] = "",
    fill: Annotated[str, Form()] = "",
    overwrite: Annotated[bool, Form()] = True,
    apply: Annotated[bool, Form()] = False,
) -> ReferenceResult:
    """补传一份参照表，按共同字段回填候选；apply=false 时只预览命中情况。"""
    task = await _task_for(session, user, task_id)
    spec = get_dataset(task.dataset_code)
    filename = file.filename or "参照表"
    content = await file.read()
    sheets = read_sheets(spec, _reference_document(filename, file.content_type, content))
    if not sheets:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"参照表里没有能对应到「{spec.name}」字段的列，请检查表头",
        )
    rows = (
        await session.scalars(
            select(IngestCandidate)
            .where(IngestCandidate.task_id == task.id, IngestCandidate.record_id.is_(None))
            .order_by(IngestCandidate.seq)
        )
    ).all()
    values = {row.id: dict(row.values or {}) for row in rows}

    current = list(values.values())
    chosen = next((item for item in sheets if item.name == sheet), None)
    if chosen is None:
        chosen = max(sheets, key=lambda item: (bool(suggest_key(item, current)), len(item.rows)))
    key_codes = _codes(key, chosen) or suggest_key(chosen, current)
    fill_codes = [code for code in _codes(fill, chosen) if code not in key_codes]
    if not fill:
        fill_codes = [code for code in chosen.fields if code not in key_codes]
    outcome = compare(chosen, values, key_codes, fill_codes, overwrite=overwrite)

    ready = 0
    if apply and outcome.updates:
        ctx = await _context(session, {spec.code})
        source = {"source": "reference", "ref": filename[:120], "score": 0.95}
        by_id = {row.id: row for row in rows}
        for candidate_id, changes in outcome.updates.items():
            row = by_id[candidate_id]
            await _reassess(
                session, row, {**values[candidate_id], **changes}, source=source, ctx=ctx
            )
        await session.commit()
        ready = sum(
            1
            for row in rows
            if not row.errors and not row.duplicate_of and "无权填写" not in (row.warnings or [])
        )

    labels = {item.code: item.label for item in spec.fields}
    return ReferenceResult(
        file_name=filename,
        sheets=[
            ReferenceSheet(
                name=item.name,
                rows=len(item.rows),
                columns=[
                    ReferenceColumn(
                        header=column.header,
                        field=column.field,
                        label=labels.get(column.field) if column.field else None,
                    )
                    for column in item.columns
                    if column.header
                ],
            )
            for item in sheets
        ],
        sheet=chosen.name,
        key=outcome.key,
        fill=outcome.fill,
        overwrite=overwrite,
        candidates=len(rows),
        matched=outcome.matched,
        unmatched=outcome.unmatched,
        ambiguous=outcome.ambiguous,
        changed=len(outcome.updates),
        overwritten=outcome.overwritten,
        unmatched_samples=outcome.unmatched_samples,
        applied=apply and bool(outcome.updates),
        ready=ready,
    )


@router.post("/api/ingestion/candidates/{candidate_id}/complete", response_model=CompleteResult)
async def complete_candidate(candidate_id: str, session: DbSession, user: Parser) -> CompleteResult:
    row = await session.get(IngestCandidate, candidate_id)
    if row is None or row.record_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="候选不存在或已确认")
    task = await _task_for(session, user, row.task_id)
    owner = await session.get(User, task.created_by)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="任务发起人不存在")
    spec = get_dataset(row.dataset_code or task.dataset_code)
    missing = missing_required(spec, row.values or {})
    if not missing:
        return CompleteResult(candidate=_candidate(row), filled=[], message="没有缺失的必填字段")
    if not row.source_text:
        return CompleteResult(candidate=_candidate(row), filled=[], message="没有可核验的原文")
    _provider, _base, key, _model = resolved_ai()
    if not key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="模型服务未配置")
    lookups, option_sets, names = await _load_context(session)
    found, _ = await load_dict_options(session)
    options = {code: [(item.value, item.label) for item in items] for code, items in found.items()}
    caller = Caller(
        session,
        task,
        HttpxLLMClient(),
        budget=task.llm_calls + 5,
        cache_enabled=True,
    )
    payload = completion_input(spec, missing, row.values or {}, row.source_text)
    result = await complete_fields(caller, spec, options, payload, task.user_prompt)
    filled, warnings = ground(result.values, result.evidence, row.source_text)
    kept = {code: value for code, value in filled.items() if code in missing}
    if not kept:
        await session.commit()
        return CompleteResult(
            candidate=_candidate(row), filled=[], message="原文中没有可核验的补充值"
        )
    values = {**(row.values or {}), **kept}
    verdict = await assess(session, task, spec, owner, values, lookups, option_sets, names, None)
    row.values = verdict.values
    sources = dict(row.field_sources or {})
    for code in kept:
        sources[code] = {
            "source": "completion",
            "score": 0.7,
            "evidence": result.evidence[:200],
        }
    row.field_sources = sources
    row.errors = verdict.errors
    row.completeness = verdict.completeness
    row.triage = verdict.triage
    row.duplicate_of = verdict.duplicate_of
    row.business_key = verdict.business_key
    row.warnings = [*(row.warnings or []), *warnings]
    await session.commit()
    return CompleteResult(candidate=_candidate(row), filled=sorted(kept), message="已用原文补全")


async def _confirm_rows(
    session: DbSession,
    user: User,
    rows: list[IngestCandidate],
    *,
    submit: bool,
    batch_id: str | None = None,
) -> ConfirmResult:
    for row in rows:
        spec = get_dataset(row.dataset_code)
        if not can_fill(user, spec):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"无权填写{spec.name}")
        if row.record_id:
            continue
        if row.errors or row.duplicate_of or "无权填写" in (row.warnings or []):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="存在校验错误或重复记录，不能确认"
            )
        missing = _missing_key(spec, row.values or {})
        if missing:
            labels = "、".join(spec.field_map()[code].label for code in missing)
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"第 {row.seq} 条缺少业务主键：{labels}，补齐后才能写入",
            )
    created = 0
    updated = 0
    submitted = 0
    for row in rows:
        if row.record_id:
            continue
        task = await session.get(IngestTask, row.task_id)
        if task is None:
            continue
        spec = get_dataset(row.dataset_code or task.dataset_code)
        record: BizRecord | None = None
        if row.target_record_id:
            existing = await session.get(BizRecord, row.target_record_id)
            if existing is not None and existing.status in {"draft", "returned"}:
                merged = {**(existing.payload or {}), **(row.values or {})}
                record = await update_record(
                    session,
                    user,
                    spec,
                    existing,
                    merged,
                    strict=False,
                    errors=list(row.errors or []),
                    completeness=row.completeness,
                    field_sources=row.field_sources or {},
                )
                updated += 1
        if record is None:
            record = await create_record(
                session,
                user,
                spec,
                row.values,
                source_type="ai",
                strict=False,
                errors=list(row.errors or []),
                completeness=row.completeness,
                field_sources=row.field_sources or {},
                source_ref=row.id,
                batch_id=batch_id or task.batch_id or task.id,
            )
            created += 1
        row.record_id = record.id
        row.status = "confirmed"
        if submit:
            await submit_record(session, user, spec, record)
            submitted += 1
    return ConfirmResult(created=created, submitted=submitted, updated=updated)


@router.post("/api/ingestion/tasks/{task_id}/confirm", response_model=ConfirmResult)
async def confirm_task(
    task_id: str, body: ConfirmWrite, session: DbSession, user: Parser
) -> ConfirmResult:
    task = await _task_for(session, user, task_id)
    rows = (
        await session.scalars(
            select(IngestCandidate).where(
                IngestCandidate.task_id == task.id,
                IngestCandidate.id.in_(body.candidate_ids),
            )
        )
    ).all()
    if len(rows) != len(set(body.candidate_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="候选不存在")
    result = await _confirm_rows(session, user, list(rows), submit=body.submit)
    remaining = await session.scalar(
        select(func.count())
        .select_from(IngestCandidate)
        .where(IngestCandidate.task_id == task.id, IngestCandidate.status == "pending")
    )
    if not remaining:
        task.status = "completed"
        task.finished_at = _now()
    await session.commit()
    return result


async def _batch_read(session: DbSession, batch: IngestBatch) -> BatchRead:
    task_count = await session.scalar(
        select(func.count()).select_from(IngestTask).where(IngestTask.batch_id == batch.id)
    )
    counts = dict(
        (
            await session.execute(
                select(IngestCandidate.triage, func.count())
                .where(IngestCandidate.batch_id == batch.id)
                .group_by(IngestCandidate.triage)
            )
        ).all()
    )
    return BatchRead(
        id=batch.id,
        title=batch.title,
        dataset_codes=list(batch.dataset_codes or []),
        status=batch.status,
        task_count=int(task_count or 0),
        candidate_count=sum(counts.values()),
        auto_count=int(counts.get("auto", 0)),
        review_count=int(counts.get("review", 0)),
        missing_count=int(counts.get("missing", 0)),
        duplicate_count=int(counts.get("duplicate", 0)),
        created_at=batch.created_at,
    )


@router.post("/api/ingestion/batches", response_model=BatchRead)
async def create_batch(body: BatchCreate, session: DbSession, user: Parser) -> BatchRead:
    specs = [get_dataset(code) for code in dict.fromkeys(body.dataset_codes)]
    for spec in specs:
        if not can_fill(user, spec):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"无权填写{spec.name}")
    title = body.title.strip() or f"{specs[0].name}批量填报"
    batch = IngestBatch(
        id=uuid_hex(),
        title=title[:120],
        dataset_codes=[spec.code for spec in specs],
        created_by=user.id,
        department_id=user.department_id,
        status="collecting",
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(batch)
    await session.commit()
    return await _batch_read(session, batch)


@router.get("/api/ingestion/batches", response_model=list[BatchRead])
async def list_batches(session: DbSession, user: Parser) -> list[BatchRead]:
    query = select(IngestBatch).order_by(IngestBatch.created_at.desc()).limit(50)
    if not is_center(user):
        query = query.where(IngestBatch.created_by == user.id)
    rows = (await session.scalars(query)).all()
    return [await _batch_read(session, row) for row in rows]


async def _gaps(session: DbSession, batch: IngestBatch) -> list[GapRead]:
    rows = (
        await session.scalars(
            select(IngestCandidate).where(
                IngestCandidate.batch_id == batch.id,
                IngestCandidate.status == "pending",
            )
        )
    ).all()
    counts: dict[tuple[str, str], int] = {}
    reasons: dict[tuple[str, str], str] = {}
    for row in rows:
        spec = get_dataset(row.dataset_code)
        for code in missing_required(spec, row.values or {}):
            key = (spec.code, code)
            counts[key] = counts.get(key, 0) + 1
            reasons[key] = "missing"
    tasks = (await session.scalars(select(IngestTask).where(IngestTask.batch_id == batch.id))).all()
    for task in tasks:
        dry = task.dry_run or {}
        gaps = dry.get("gaps") if isinstance(dry, dict) else None
        for gap in gaps or []:
            if not isinstance(gap, dict):
                continue
            code = str(gap.get("code") or "")
            key = (task.dataset_code, code)
            if key in counts:
                continue
            counts[key] = 0
            reasons[key] = str(gap.get("reason") or "no_column")
    result: list[GapRead] = []
    for (dataset_code, code), count in sorted(counts.items(), key=lambda item: -item[1]):
        spec = get_dataset(dataset_code)
        entity = spec.field_map().get(code)
        result.append(
            GapRead(
                dataset_code=dataset_code,
                dataset_name=spec.name,
                code=code,
                label=entity.label if entity else code,
                count=count,
                reason=reasons.get((dataset_code, code), "missing"),
            )
        )
    return result


@router.get("/api/ingestion/batches/{batch_id}")
async def read_batch(batch_id: str, session: DbSession, user: Parser) -> dict[str, object]:
    batch = await _batch_for(session, user, batch_id)
    tasks = (
        await session.scalars(
            select(IngestTask)
            .where(IngestTask.batch_id == batch.id)
            .order_by(IngestTask.created_at)
        )
    ).all()
    return {
        "batch": (await _batch_read(session, batch)).model_dump(mode="json"),
        "tasks": [(await _read(session, task)).model_dump(mode="json") for task in tasks],
        "gaps": [gap.model_dump(mode="json") for gap in await _gaps(session, batch)],
    }


@router.post(
    "/api/ingestion/batches/{batch_id}/files",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestTaskRead,
)
async def upload_batch_file(
    batch_id: str,
    session: DbSession,
    user: Parser,
    dataset_code: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    prompt: Annotated[str, Form()] = "",
    fresh_plan: Annotated[bool, Form()] = False,
) -> IngestTaskRead:
    batch = await _batch_for(session, user, batch_id)
    if dataset_code not in set(batch.dataset_codes or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该数据表不在本批次内")
    task = await _create_task(
        session, user, dataset_code, file, prompt, batch.id, fresh_plan=fresh_plan
    )
    return await _read(session, task)


@router.get(
    "/api/ingestion/batches/{batch_id}/candidates",
    response_model=list[IngestCandidateRead],
)
async def list_batch_candidates(
    batch_id: str,
    session: DbSession,
    user: Parser,
    triage: str | None = None,
    dataset_code: str | None = None,
    offset: int = 0,
    limit: int = 200,
) -> list[IngestCandidateRead]:
    batch = await _batch_for(session, user, batch_id)
    query = select(IngestCandidate).where(IngestCandidate.batch_id == batch.id)
    if triage:
        query = query.where(IngestCandidate.triage == triage)
    if dataset_code:
        query = query.where(IngestCandidate.dataset_code == dataset_code)
    query = query.order_by(IngestCandidate.seq).offset(max(offset, 0)).limit(min(limit, 500))
    rows = (await session.scalars(query)).all()
    return [_candidate(row) for row in rows]


@router.get("/api/ingestion/batches/{batch_id}/gaps", response_model=list[GapRead])
async def batch_gaps(batch_id: str, session: DbSession, user: Parser) -> list[GapRead]:
    return await _gaps(session, await _batch_for(session, user, batch_id))


@router.post("/api/ingestion/batches/{batch_id}/confirm", response_model=ConfirmResult)
async def confirm_batch(
    batch_id: str, body: ConfirmWrite, session: DbSession, user: Parser
) -> ConfirmResult:
    batch = await _batch_for(session, user, batch_id)
    rows = (
        await session.scalars(
            select(IngestCandidate).where(
                IngestCandidate.batch_id == batch.id,
                IngestCandidate.id.in_(body.candidate_ids),
            )
        )
    ).all()
    if len(rows) != len(set(body.candidate_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="候选不存在")
    result = await _confirm_rows(session, user, list(rows), submit=body.submit, batch_id=batch.id)
    pending = await session.scalar(
        select(func.count())
        .select_from(IngestCandidate)
        .where(IngestCandidate.batch_id == batch.id, IngestCandidate.status == "pending")
    )
    batch.status = "reviewing" if pending else "completed"
    batch.updated_at = _now()
    await session.commit()
    return result


@router.get("/api/ingestion/templates", response_model=list[TemplateRead])
async def list_templates(
    session: DbSession, user: Parser, dataset_code: str | None = None
) -> list[TemplateRead]:
    _ = user
    query = select(IngestPlanTemplate).order_by(IngestPlanTemplate.last_used_at.desc())
    if dataset_code:
        query = query.where(IngestPlanTemplate.dataset_code == dataset_code)
    rows = (await session.scalars(query.limit(200))).all()
    return [
        TemplateRead(
            id=row.id,
            dataset_code=row.dataset_code,
            signature=row.signature,
            scope=row.scope,
            department_id=row.department_id,
            hits=row.hits,
            updated_at=row.last_used_at,
        )
        for row in rows
    ]


@router.delete("/api/ingestion/templates/{template_id}", status_code=204)
async def delete_template(template_id: str, session: DbSession, user: Parser) -> None:
    if not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只有信息中心可以删除模板")
    row = await session.get(IngestPlanTemplate, template_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="模板不存在")
    await session.delete(row)
    await session.commit()


@router.get("/api/ingestion/aliases", response_model=list[AliasRead])
async def list_aliases(
    session: DbSession, user: Parser, dataset_code: str | None = None
) -> list[AliasRead]:
    _ = user
    query = select(IngestHeaderAlias).order_by(IngestHeaderAlias.created_at.desc())
    if dataset_code:
        query = query.where(IngestHeaderAlias.dataset_code == dataset_code)
    rows = (await session.scalars(query.limit(500))).all()
    return [
        AliasRead(
            id=row.id,
            dataset_code=row.dataset_code,
            header_norm=row.header_norm,
            header_raw=row.header_raw,
            field_code=row.field_code,
            scope=row.scope,
            hits=row.hits,
        )
        for row in rows
    ]


@router.delete("/api/ingestion/aliases/{alias_id}", status_code=204)
async def delete_alias(alias_id: str, session: DbSession, user: Parser) -> None:
    if not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只有信息中心可以删除别名")
    row = await session.get(IngestHeaderAlias, alias_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="别名不存在")
    await session.delete(row)
    await session.commit()


async def _purgeable_records(
    session: DbSession, rows: list[IngestCandidate], *, purge_records: bool
) -> dict[str, BizRecord]:
    """按候选 id 挑出可以随任务一起清除的草稿；不能删除时抛 400，避免删一半。"""
    record_ids = {row.record_id for row in rows if row.record_id}
    if not record_ids:
        return {}
    if not purge_records:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"该任务已生成 {len(record_ids)} 条草稿，需勾选“同时清除已生成的草稿”后才能删除",
        )
    records = (await session.scalars(select(BizRecord).where(BizRecord.id.in_(record_ids)))).all()
    by_id: dict[str, BizRecord] = {}
    for record in records:
        if record.deleted_at is not None:
            continue
        # 手工创建的记录只是被解析结果补充过，不随任务清除，保留给用户。
        if record.source_type != "ai":
            continue
        if record.status not in {"draft", "returned"}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"记录「{record.business_key}」已提交审核或已发布，请先撤回后再清除",
            )
        by_id[record.id] = record
    return {
        row.id: by_id[row.record_id]
        for row in rows
        if row.record_id is not None and row.record_id in by_id
    }


async def _purge_task(
    session: DbSession,
    task: IngestTask,
    rows: list[IngestCandidate],
    records: dict[str, BizRecord],
) -> int:
    """删除任务、候选、上传文件和本任务对应的草稿，返回清除的草稿数。"""
    cleared = 0
    targets: dict[str, BizRecord] = {}
    for row in rows:
        record = records.get(row.id)
        if record is not None:
            targets[record.id] = record
    if targets:
        # 先解除其他候选对这批草稿的引用，再删记录，避免外键约束冲突。
        await session.execute(
            update(IngestCandidate)
            .where(IngestCandidate.target_record_id.in_(list(targets)))
            .values(target_record_id=None)
        )
    for row in rows:
        await session.delete(row)
    await session.flush()
    for record in targets.values():
        await session.delete(record)
        cleared += 1
    stored = await session.scalar(select(IngestFile).where(IngestFile.task_id == task.id))
    if stored is not None:
        delete_upload(stored.stored_path)
        await session.delete(stored)
    await session.delete(task)
    return cleared


@router.delete("/api/ingestion/tasks/{task_id}")
async def delete_task(
    task_id: str,
    session: DbSession,
    user: Parser,
    purge_records: bool = False,
) -> dict[str, int]:
    task = await _task_for(session, user, task_id)
    rows = list(
        (
            await session.scalars(select(IngestCandidate).where(IngestCandidate.task_id == task.id))
        ).all()
    )
    records = await _purgeable_records(session, rows, purge_records=purge_records)
    cleared = await _purge_task(session, task, rows, records)
    await session.commit()
    return {"deleted_tasks": 1, "cleared_records": cleared}


@router.delete("/api/ingestion/batches/{batch_id}")
async def delete_batch(
    batch_id: str,
    session: DbSession,
    user: Parser,
    purge_records: bool = False,
) -> dict[str, int]:
    """删除整批：先校验全部任务，再统一删除，避免只删掉一部分。"""
    batch = await _batch_for(session, user, batch_id)
    tasks = list(
        (await session.scalars(select(IngestTask).where(IngestTask.batch_id == batch.id))).all()
    )
    rows_by_task = {
        task.id: list(
            (
                await session.scalars(
                    select(IngestCandidate).where(IngestCandidate.task_id == task.id)
                )
            ).all()
        )
        for task in tasks
    }
    all_rows = [row for rows in rows_by_task.values() for row in rows]
    records = await _purgeable_records(session, all_rows, purge_records=purge_records)
    cleared = 0
    for task in tasks:
        cleared += await _purge_task(session, task, rows_by_task[task.id], records)
    await session.delete(batch)
    await session.commit()
    return {"deleted_tasks": len(tasks), "cleared_records": cleared}
