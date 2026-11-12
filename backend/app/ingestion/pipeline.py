"""解析、规划、执行、补全、校验、分诊，最后写入候选。确认前不生成填报记录。"""

import logging
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.calls import BudgetExceeded, Caller, OutputInvalid
from app.ai.client import HttpxLLMClient, LLMClient, ModelUnavailable
from app.ai.extract import (
    COMPLETE_VERSION,
    RECORD_VERSION,
    complete_fields,
    extract_records,
)
from app.ai.schema import completion_input, field_guide
from app.core.config import resolved_ai, settings
from app.datasets.access import filler_type_for
from app.datasets.registry import get_dataset
from app.datasets.spec import DatasetSpec, jsonable
from app.ingestion import dedupe, rounds, supplement, triage
from app.ingestion.chunking import chunk_blocks
from app.ingestion.dedupe import KeyIndex
from app.ingestion.enrich import LookupCache, enrich
from app.ingestion.execute import build_records
from app.ingestion.grounding import ground
from app.ingestion.normalize import cell_text, normalize_payload
from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.parsers.docx import parse_docx
from app.ingestion.parsers.pdf import parse_pdf
from app.ingestion.parsers.spreadsheet import (
    estimate_xlsx_cells,
    parse_csv,
    parse_xls,
    parse_xlsx,
)
from app.ingestion.plan import SheetPlan, StructurePlan, mapped_fields
from app.ingestion.planning import (
    PlanInvalid,
    auto_execute,
    dry_run,
    exact_for,
    plan_with_model,
    validate_plan,
)
from app.ingestion.profile import DocumentProfile, profile_document
from app.ingestion.storage import read_upload
from app.ingestion.templates import find_template, load_aliases, use_template
from app.models.ingestion import IngestBatch, IngestCandidate, IngestFile, IngestTask
from app.models.system import User
from app.schemas.staff import DictOption
from app.services.staff import active_department_names, load_dict_options

logger = logging.getLogger(__name__)
_SCAN = "首版不支持扫描件识别，请上传可复制文字的 PDF 或改用表格"
_BATCH = 20
_EMPTY = "不能为空"


class IngestFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message


@dataclass
class Verdict:
    values: dict[str, object]
    errors: list[str]
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    duplicate_of: str | None = None
    target_record_id: str | None = None
    field_sources: dict[str, dict[str, object]] = field(default_factory=dict)
    conflicts: list[dict[str, object]] = field(default_factory=list)
    completeness: int = 0
    triage: str = triage.TRIAGE_REVIEW
    business_key: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


async def _checkpoint(session: AsyncSession, task: IngestTask, progress: int) -> None:
    """提交进度和心跳，前端轮询与卡住恢复只能看到已提交的状态。"""
    task.progress = progress
    task.heartbeat_at = _now()
    await session.commit()
    await session.refresh(task, ["cancel_requested"])


async def run_pipeline(
    session: AsyncSession, task_id: str, client: LLMClient | None = None
) -> None:
    task = await session.get(IngestTask, task_id)
    if task is None or task.status in {"completed", "cancelled"}:
        return
    started = time.monotonic()
    task.attempts += 1
    task.status = "parsing"
    task.progress = 10
    task.started_at = task.started_at or _now()
    task.heartbeat_at = _now()
    task.error_code = None
    task.error_message = None
    task.finished_at = None
    await session.commit()
    try:
        if task.cancel_requested:
            task.status = "cancelled"
            task.finished_at = _now()
            return
        await _execute(session, task, client)
    except IngestFailure as exc:
        _fail(task, exc.code, exc.message)
    except ModelUnavailable:
        _fail(task, "model_unavailable", "模型服务暂不可用")
    except BudgetExceeded:
        _fail(task, "budget_exceeded", "模型调用次数超过任务上限")
    except OutputInvalid:
        _fail(task, "model_output", "模型输出无法解析")
    except FileNotFoundError:
        _fail(task, "file_missing", "原始文件不存在")
    except Exception:
        logger.exception("ingest task=%s", task.id)
        _fail(task, "internal", "解析过程出现错误")
    finally:
        task.duration_ms += int((time.monotonic() - started) * 1000)
        if task.batch_id and task.status in {
            "awaiting_plan",
            "pending_confirmation",
            "completed",
        }:
            batch = await session.get(IngestBatch, task.batch_id)
            if batch is not None and batch.status in {"collecting", "parsing"}:
                batch.status = "reviewing"
                batch.updated_at = _now()
        await session.flush()
        if task.llm_calls and task.status in {"pending_confirmation", "completed"}:
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(IngestCandidate)
                    .where(IngestCandidate.task_id == task.id)
                )
                or 0
            )
            if total and task.llm_calls / total > 0.5:
                sheets = (task.plan or {}).get("sheets") or []
                names = [str(sheet.get("sheet")) for sheet in sheets if isinstance(sheet, dict)]
                logger.warning(
                    "ingest task=%s ratio=%.2f calls=%s records=%s sheets=%s",
                    task.id,
                    task.llm_calls / total,
                    task.llm_calls,
                    total,
                    names,
                )


async def _execute(session: AsyncSession, task: IngestTask, client: LLMClient | None) -> None:
    stored = await session.scalar(select(IngestFile).where(IngestFile.task_id == task.id))
    if stored is None:
        raise IngestFailure("file_missing", "原始文件不存在")
    document = _parse(stored.stored_path, read_upload(stored.stored_path))
    _guard_document(stored.stored_path, document)
    stored.page_count = document.page_count or None
    stored.row_count = document.row_count or None
    specs = await _target_specs(session, task)
    profile = profile_document(document)
    task.profile = profile.model_dump(mode="json")
    task.plan_source = None
    task.dry_run = None
    await session.execute(
        delete(IngestCandidate).where(
            IngestCandidate.task_id == task.id, IngestCandidate.record_id.is_(None)
        )
    )
    before = await rounds.snapshot(session, task.batch_id) if task.batch_id else {}
    task.status = "extracting"
    await _checkpoint(session, task, 30)
    user = await session.get(User, task.created_by)
    if user is None:
        raise IngestFailure("user_missing", "发起人不存在")
    found, option_sets = await load_dict_options(session)
    lookups = _lookups(found)
    options = _guide_options(found)
    guides = {code: field_guide(spec, options) for code, spec in specs.items()}
    names = set(await active_department_names(session))
    provider, _base, _key, model = resolved_ai()
    task.llm_provider = provider
    task.llm_model = model
    task.schema_version = specs[task.dataset_code].schema_version
    caller = _caller(session, task, client, guides)
    index = KeyIndex()
    await index.load(session, set(specs))
    cache = LookupCache()
    merge_index = await _merge_index(session, task, set(specs))
    seen: dict[str, str] = {}
    seq = 0
    plan: StructurePlan | None = None
    usable = [sheet for sheet in profile.sheets if not sheet.skip_reason]
    if task.mode != "initial" and usable and task.batch_id:
        handled = await _supplement(
            session,
            task,
            specs[task.dataset_code],
            document,
            profile,
            user,
            lookups,
            option_sets,
            names,
            caller,
            guides,
            index,
            cache,
        )
        if handled:
            if task.status != "awaiting_plan":
                task.prompt_version = task.plan_source
                task.status = "pending_confirmation"
                task.progress = 100
                task.finished_at = _now()
            await _round(session, task, before, stored.original_name)
            if task.status == "awaiting_plan":
                await _checkpoint(session, task, 55)
            return
    if task.mode != "initial":
        task.mode = "initial"
    if usable:
        plan = await _resolve_plan(session, task, specs, profile, guides, caller)
        task.plan = plan.model_dump(mode="json")
        task.plan_source = plan.source
        dry = dry_run(document, plan, specs)
        task.dry_run = dry.model_dump(mode="json")
        if not auto_execute(plan, dry) and not task.mapping_applied:
            task.status = "awaiting_plan"
            await _round(session, task, before, stored.original_name)
            await _checkpoint(session, task, 55)
            logger.info("ingest task=%s awaiting plan source=%s", task.id, plan.source)
            return
        await _checkpoint(session, task, 60)
        seq = await _tables(
            session,
            task,
            specs,
            document,
            plan,
            user,
            lookups,
            options,
            option_sets,
            names,
            caller,
            index,
            cache,
            merge_index,
            seen,
            seq,
        )
        if task.status == "cancelled":
            return
    if document.blocks:
        if caller is None:
            raise ModelUnavailable("模型服务暂不可用")
        seq = await _texts(
            session,
            task,
            specs[task.dataset_code],
            user,
            document,
            lookups,
            options,
            option_sets,
            names,
            caller,
            index,
            cache,
            merge_index,
            seen,
            seq,
        )
        if task.status == "cancelled":
            return
    task.prompt_version = _prompt_version(plan, document)
    task.status = "pending_confirmation"
    task.progress = 100
    task.finished_at = _now()
    await _round(session, task, before, stored.original_name)
    logger.info(
        "ingest task=%s candidates=%s calls=%s plan=%s",
        task.id,
        seq,
        task.llm_calls,
        plan.source if plan else "text",
    )


async def _round(
    session: AsyncSession, task: IngestTask, before: rounds.Snapshot, file_name: str
) -> None:
    """轮次报告写失败不影响解析结果，只记日志。"""
    if not task.batch_id:
        return
    extra: dict[str, object] = {
        "file_name": file_name,
        "mode": task.mode,
        "plan_source": task.plan_source,
        "status": task.status,
    }
    dry = task.dry_run or {}
    if isinstance(dry.get("supplement"), dict):
        extra["supplement"] = dry["supplement"]
    try:
        await rounds.record(
            session,
            task.batch_id,
            trigger="file",
            before=before,
            user_id=task.created_by,
            dataset_code=task.dataset_code,
            task_id=task.id,
            extra=extra,
        )
    except Exception:
        logger.exception("ingest round task=%s", task.id)


async def _supplement(
    session: AsyncSession,
    task: IngestTask,
    spec: DatasetSpec,
    document: ParsedDocument,
    profile: DocumentProfile,
    user: User,
    lookups: dict[str, dict[str, str]],
    option_sets: dict[str, set[str]],
    names: set[str],
    caller: Caller | None,
    guides: dict[str, str],
    index: KeyIndex,
    cache: LookupCache,
) -> bool:
    """补齐模式。返回 False 表示这份文件应按首轮处理（批次里还没有该表候选，或文件本身已完整）。"""
    if task.batch_id is None:
        return False
    rows = [
        row
        for row in await rounds.pending_rows(session, task.batch_id)
        if row.dataset_code == spec.code
    ]
    if not rows:
        return False
    marker = supplement.read_marker(document)
    if marker is not None and (
        marker.batch_id != task.batch_id or marker.dataset_code != spec.code
    ):
        marker = None
    aliases = await load_aliases(session, {spec.code}, task.department_id)
    extra = aliases.get(spec.code, {})
    user_plan = bool(task.mode == "supplement" and task.mapping_applied and task.plan)
    if marker is None and not user_plan and exact_for({spec.code: spec}, profile, aliases):
        return False
    task.mode = "supplement"
    candidates = {row.id: dict(row.values or {}) for row in rows}
    preferred = tuple(task.match_key) if task.match_key else None
    options = supplement.key_options(spec, preferred, marker.key if marker else None)
    sheet_plan: SheetPlan | None = None
    source = "exact"
    confidence = 1.0
    if user_plan:
        stored = StructurePlan.model_validate(task.plan)
        sheet_plan = next(
            (
                item
                for item in stored.sheets
                if item.role == "main" and item.dataset_code == spec.code
            ),
            None,
        )
        source = "user"
    if sheet_plan is None and task.fresh_plan and marker is None and caller is not None:
        modeled = await _supplement_model_plan(task, spec, profile, guides, caller)
        if modeled is not None:
            sheet_plan, confidence = modeled
            source = "llm"
    if sheet_plan is None:
        sheet_plan = supplement.partial_plan(spec, profile, extra)
        source = "supplement" if marker else "exact"
    key = (
        supplement.choose_key(mapped_fields(sheet_plan), candidates, options)
        if sheet_plan is not None
        else None
    )
    if key is None and marker is None and not user_plan and source != "llm" and caller is not None:
        modeled = await _supplement_model_plan(task, spec, profile, guides, caller)
        if modeled is not None:
            found = supplement.choose_key(mapped_fields(modeled[0]), candidates, options)
            if found is not None:
                sheet_plan, confidence, key = modeled[0], modeled[1], found
                source = "llm"
    if sheet_plan is None:
        raise IngestFailure("supplement_unreadable", "补齐文件中没有能对应到标准字段的表头")
    plan = StructurePlan(sheets=[sheet_plan], source=source, confidence=confidence)
    task.plan = plan.model_dump(mode="json")
    task.plan_source = source
    dry = dry_run(document, plan, {spec.code: spec}).model_dump(mode="json")
    if key is None:
        tried = "、".join(
            "+".join(spec.field_map()[code].label for code in option if code in spec.field_map())
            for option in options
        )
        dry["supplement"] = {
            "error": f"文件中没有能唯一对上已有记录的字段组合（可用：{tried}）",
            "rows": 0,
            "matched": 0,
        }
        task.dry_run = dry
        if user_plan:
            raise IngestFailure("supplement_key", str(dry["supplement"]["error"]))
        task.status = "awaiting_plan"
        return True
    task.match_key = list(key)
    fields = tuple(
        code for code in mapped_fields(sheet_plan) if code not in key and code in spec.field_map()
    )
    execution = build_records(document, plan)
    file_rows: list[tuple[dict[str, object], dict[str, object]]] = []
    for record in execution.records:
        if not record.raw:
            continue
        normalized = normalize_payload(spec, record.raw, lookups)
        values = {code: normalized[code] for code, raw in record.raw.items() if cell_text(raw)}
        file_rows.append((values, {"sheet": record.sheet, "row": record.row}))
    outcome = supplement.match(spec, key, fields, file_rows, candidates)
    dry["supplement"] = outcome.summary(spec)
    task.dry_run = dry
    auto = (
        marker is not None
        or bool(user_plan)
        or (
            outcome.matched > 0
            and outcome.match_rate >= settings.supplement_min_match_rate
            and outcome.conflict_rate <= settings.supplement_max_conflict_rate
            and (source != "llm" or confidence >= 0.8)
        )
    )
    if not auto:
        task.status = "awaiting_plan"
        logger.info(
            "ingest task=%s supplement awaiting rate=%.2f conflicts=%s",
            task.id,
            outcome.match_rate,
            outcome.conflict_rows,
        )
        return True
    await _apply_fills(
        session, task, spec, user, outcome, source, lookups, option_sets, names, index, cache
    )
    return True


async def _supplement_model_plan(
    task: IngestTask,
    spec: DatasetSpec,
    profile: DocumentProfile,
    guides: dict[str, str],
    caller: Caller,
) -> tuple[SheetPlan, float] | None:
    """表头对不上时让模型给出列映射；模型不可用或计划无效都按“需要确认”处理。"""
    try:
        plan = await plan_with_model(caller, {spec.code: spec}, profile, guides, task.user_prompt)
        plan = validate_plan(plan, profile, {spec.code: spec})
    except (OutputInvalid, PlanInvalid, ModelUnavailable, BudgetExceeded) as exc:
        logger.info("supplement model plan task=%s failed: %s", task.id, exc)
        return None
    sheet = next((item for item in plan.sheets if item.role == "main"), None)
    if sheet is None:
        return None
    return sheet, plan.confidence


async def _apply_fills(
    session: AsyncSession,
    task: IngestTask,
    spec: DatasetSpec,
    user: User,
    outcome: supplement.Outcome,
    source: str,
    lookups: dict[str, dict[str, str]],
    option_sets: dict[str, set[str]],
    names: set[str],
    index: KeyIndex,
    cache: LookupCache,
) -> None:
    if not outcome.fills:
        return
    locked = (
        await session.scalars(
            select(IngestCandidate)
            .where(IngestCandidate.id.in_(list(outcome.fills)))
            .with_for_update()
        )
    ).all()
    score = 0.85 if source == "llm" else 0.95
    for row in locked:
        fill = outcome.fills[row.id]
        values = dict(row.values or {})
        sources = {
            code: item for code, item in (row.field_sources or {}).items() if isinstance(item, dict)
        }
        raw_values = dict(row.raw_values or {})
        for code, value in fill.updates.items():
            # 加锁前可能已被其他文件或用户填上，只补仍为空的字段
            if cell_text(values.get(code)):
                continue
            values[code] = value
            raw_values[code] = value
            sources[code] = {
                "source": "file",
                "score": score,
                "ref": {"task": task.id, **fill.location},
            }
        verdict = await assess(
            session,
            task,
            spec,
            user,
            values,
            lookups,
            option_sets,
            names,
            None,
            index,
            cache,
            field_sources=sources,
        )
        conflicts = list(row.conflicts or [])
        for conflict in fill.conflicts:
            if conflict not in conflicts:
                conflicts.append(conflict)
        warnings = list(verdict.warnings)
        if conflicts:
            warnings = _unique(warnings, "同批次存在字段冲突")
        row.raw_values = raw_values
        row.values = verdict.values
        row.field_sources = cast(dict[str, object], verdict.field_sources)
        row.conflicts = conflicts
        row.errors = verdict.errors
        row.warnings = warnings
        row.completeness = verdict.completeness
        row.business_key = verdict.business_key
        row.duplicate_of = verdict.duplicate_of
        row.target_record_id = verdict.target_record_id
        row.triage = (
            triage.TRIAGE_REVIEW if conflicts and not verdict.duplicate_of else verdict.triage
        )
    await session.flush()


def _caller(
    session: AsyncSession,
    task: IngestTask,
    client: LLMClient | None,
    guides: dict[str, str],
) -> Caller | None:
    if client is None:
        _provider, _base, key, _model = resolved_ai()
        if not key:
            return None
        client = HttpxLLMClient()
    _ = guides
    return Caller(
        session,
        task,
        client,
        budget=settings.ingest_llm_budget,
        cache_enabled=client.__class__ is HttpxLLMClient,
    )


async def _target_specs(session: AsyncSession, task: IngestTask) -> dict[str, DatasetSpec]:
    codes = [task.dataset_code]
    if task.batch_id:
        batch = await session.get(IngestBatch, task.batch_id)
        if batch is not None:
            codes = [*list(batch.dataset_codes or []), task.dataset_code]
    return {code: get_dataset(code) for code in dict.fromkeys(codes)}


async def _resolve_plan(
    session: AsyncSession,
    task: IngestTask,
    specs: dict[str, DatasetSpec],
    profile: object,
    guides: dict[str, str],
    caller: Caller | None,
) -> StructurePlan:
    from app.ingestion.profile import DocumentProfile

    if not isinstance(profile, DocumentProfile):
        raise IngestFailure("internal", "文件画像缺失")
    if task.plan and task.mapping_applied:
        stored = StructurePlan.model_validate(task.plan)
        stored = stored.model_copy(update={"source": "user", "confidence": 1})
        return validate_plan(stored, profile, specs)
    # 用户要求重新识别，或写了补充说明（只有模型能读懂）时，不走模板和精确匹配
    if not (task.fresh_plan or task.user_prompt.strip()):
        aliases = await load_aliases(session, set(specs), task.department_id)
        template = await _template_plan(session, specs, profile, task.department_id)
        if template is not None:
            return validate_plan(template, profile, specs)
        if len(specs) > 1:
            primary = {task.dataset_code: specs[task.dataset_code]}
            exact_primary = exact_for(primary, profile, aliases)
            if exact_primary is not None and not _covers_other_targets(
                profile, specs, task.dataset_code, aliases
            ):
                return validate_plan(exact_primary, profile, primary)
        exact = exact_for(specs, profile, aliases)
        if exact is not None:
            return validate_plan(exact, profile, specs)
    if caller is None:
        raise ModelUnavailable("模型服务暂不可用")
    try:
        plan = await plan_with_model(caller, specs, profile, guides, task.user_prompt)
    except OutputInvalid as exc:
        reason = str(exc)
        if not reason.startswith("结构计划未通过校验"):
            raise
        logger.info("plan invalid task=%s %s", task.id, reason)
        raise IngestFailure("plan_invalid", reason[:300]) from exc
    try:
        return validate_plan(plan, profile, specs)
    except PlanInvalid as exc:
        raise IngestFailure(
            "plan_invalid", f"结构计划无法通过校验：{'；'.join(exc.errors[:3])[:300]}"
        ) from exc


def _covers_other_targets(
    profile: object,
    specs: dict[str, DatasetSpec],
    primary: str,
    aliases: dict[str, dict[str, str]],
) -> bool:
    """同一份文件里如果还能精确识别出其他数据表，就按多表计划处理。"""
    from app.ingestion.mapping import exact_plan
    from app.ingestion.profile import DocumentProfile

    if not isinstance(profile, DocumentProfile):
        return False
    for code, spec in specs.items():
        if code == primary:
            continue
        for sheet in profile.sheets:
            if sheet.skip_reason:
                continue
            if exact_plan(spec, sheet, aliases.get(code, {})) is not None:
                return True
    return False


async def _template_plan(
    session: AsyncSession,
    specs: dict[str, DatasetSpec],
    profile: object,
    department_id: int | None,
) -> StructurePlan | None:
    from app.ingestion.profile import DocumentProfile

    if not isinstance(profile, DocumentProfile):
        return None
    sheets = []
    seen: set[str] = set()
    for code in specs:
        found = None
        for sheet in profile.sheets:
            if sheet.skip_reason:
                continue
            template = await find_template(session, code, sheet.signature, department_id)
            if template is not None:
                found = template
                break
        if found is None:
            return None
        plan = await use_template(session, found)
        if any(profile.get(item.sheet) is None for item in plan.sheets):
            return None
        if {item.dataset_code for item in plan.sheets} >= set(specs):
            return plan
        for item in plan.sheets:
            if item.sheet not in seen:
                seen.add(item.sheet)
                sheets.append(item)
    return StructurePlan(sheets=sheets, source="template", confidence=1)


async def _tables(
    session: AsyncSession,
    task: IngestTask,
    specs: dict[str, DatasetSpec],
    document: ParsedDocument,
    plan: StructurePlan,
    user: User,
    lookups: dict[str, dict[str, str]],
    options: dict[str, list[tuple[str, str]]],
    option_sets: dict[str, set[str]],
    names: set[str],
    caller: Caller | None,
    index: KeyIndex,
    cache: LookupCache,
    merge_index: dict[tuple[str, str], IngestCandidate],
    seen: dict[str, str],
    seq: int,
) -> int:
    execution = build_records(document, plan)
    total = max(len(execution.records), 1)
    for position, record in enumerate(execution.records, start=1):
        if position % _BATCH == 0:
            await _checkpoint(session, task, 60 + 35 * position // total)
            if task.cancel_requested:
                task.status = "cancelled"
                task.finished_at = _now()
                return seq
        spec = specs.get(record.dataset_code)
        if spec is None:
            continue
        location: dict[str, object] = {"sheet": record.sheet, "row": record.row}
        if not record.raw:
            if caller is None:
                raise ModelUnavailable("模型服务暂不可用")
            seq = await _from_text(
                session,
                task,
                spec,
                user,
                record.source_text,
                location,
                lookups,
                options,
                option_sets,
                names,
                caller,
                index,
                cache,
                merge_index,
                seen,
                seq,
            )
            continue
        seq += 1
        await _add(
            session,
            task,
            spec,
            user,
            record.raw,
            location,
            lookups,
            option_sets,
            names,
            seen,
            index,
            cache,
            merge_index,
            seq,
            source_text=record.source_text,
            field_sources=_file_sources(plan, record.sheet_plan, record.raw),
            merge_by=record.sheet_plan.dedupe_by,
        )
    return seq


async def _texts(
    session: AsyncSession,
    task: IngestTask,
    spec: DatasetSpec,
    user: User,
    document: ParsedDocument,
    lookups: dict[str, dict[str, str]],
    options: dict[str, list[tuple[str, str]]],
    option_sets: dict[str, set[str]],
    names: set[str],
    caller: Caller,
    index: KeyIndex,
    cache: LookupCache,
    merge_index: dict[tuple[str, str], IngestCandidate],
    seen: dict[str, str],
    seq: int,
) -> int:
    task.mapping_applied = True
    for location, text in chunk_blocks(document.blocks):
        if task.cancel_requested:
            task.status = "cancelled"
            task.finished_at = _now()
            return seq
        seq = await _from_text(
            session,
            task,
            spec,
            user,
            text,
            location,
            lookups,
            options,
            option_sets,
            names,
            caller,
            index,
            cache,
            merge_index,
            seen,
            seq,
        )
    return seq


async def _from_text(
    session: AsyncSession,
    task: IngestTask,
    spec: DatasetSpec,
    user: User,
    text: str,
    location: dict[str, object],
    lookups: dict[str, dict[str, str]],
    options: dict[str, list[tuple[str, str]]],
    option_sets: dict[str, set[str]],
    names: set[str],
    caller: Caller,
    index: KeyIndex,
    cache: LookupCache,
    merge_index: dict[tuple[str, str], IngestCandidate],
    seen: dict[str, str],
    seq: int,
) -> int:
    extracted = await extract_records(caller, spec, options, text, task.user_prompt)
    for item in extracted.records:
        values, warnings = ground(item.values, item.evidence, text)
        if not values:
            continue
        seq += 1
        place = dict(location)
        if item.evidence:
            place["snippet"] = item.evidence[:80]
        sources = {
            code: {
                "source": "ai",
                "score": min(0.85, max(0.6, item.confidence or 0.7)),
                "evidence": item.evidence[:200],
            }
            for code in values
        }
        candidate = await _add(
            session,
            task,
            spec,
            user,
            values,
            place,
            lookups,
            option_sets,
            names,
            seen,
            index,
            cache,
            merge_index,
            seq,
            source_text=text,
            field_sources=sources,
        )
        for message in warnings:
            if candidate is not None and message not in candidate.warnings:
                candidate.warnings = [*candidate.warnings, message]
        if candidate is not None and settings.ingest_auto_complete:
            await _auto_complete(
                session, task, spec, user, candidate, options, caller, option_sets, names
            )
    return seq


async def _auto_complete(
    session: AsyncSession,
    task: IngestTask,
    spec: DatasetSpec,
    user: User,
    candidate: IngestCandidate,
    options: dict[str, list[tuple[str, str]]],
    caller: Caller,
    option_sets: dict[str, set[str]],
    names: set[str],
) -> None:
    missing = [
        code
        for code in triage.missing_required(spec, candidate.values)
        if code not in spec.enrich_targets()
    ]
    if not missing or len(missing) > 8 or not candidate.source_text:
        return
    if task.llm_calls >= settings.ingest_llm_budget:
        return
    payload = completion_input(spec, missing, candidate.values, candidate.source_text)
    result = await complete_fields(caller, spec, options, payload, task.user_prompt)
    filled, warnings = ground(result.values, result.evidence, candidate.source_text)
    kept = {code: value for code, value in filled.items() if code in missing}
    if not kept:
        return
    values = dict(candidate.values)
    values.update(kept)
    _refresh(spec, candidate, values, option_sets, names)
    sources = dict(candidate.field_sources or {})
    for code in kept:
        sources[code] = {
            "source": "completion",
            "score": 0.7,
            "evidence": result.evidence[:200],
        }
    candidate.field_sources = sources
    candidate.warnings = [*candidate.warnings, "已用原文补全部分字段"]
    for message in warnings:
        if message not in candidate.warnings:
            candidate.warnings = [*candidate.warnings, message]
    task.prompt_version = f"{task.plan_source or 'text'}+{COMPLETE_VERSION}"
    await session.flush()
    _ = user


async def _add(
    session: AsyncSession,
    task: IngestTask,
    spec: DatasetSpec,
    user: User,
    raw: dict[str, object],
    location: dict[str, object],
    lookups: dict[str, dict[str, str]],
    option_sets: dict[str, set[str]],
    names: set[str],
    seen: dict[str, str],
    index: KeyIndex,
    cache: LookupCache,
    merge_index: dict[tuple[str, str], IngestCandidate],
    seq: int,
    *,
    source_text: str = "",
    field_sources: dict[str, dict[str, object]] | None = None,
    merge_by: list[str] | None = None,
) -> IngestCandidate | None:
    verdict = await assess(
        session,
        task,
        spec,
        user,
        raw,
        lookups,
        option_sets,
        names,
        seen,
        index,
        cache,
        source_text=source_text,
        field_sources=field_sources,
    )
    rule_key = _rule_key(merge_by, verdict.values)
    if rule_key is not None:
        existing = merge_index.get((spec.code, rule_key))
    else:
        existing = _merge_target(merge_index, spec, verdict)
    if existing is not None:
        _merge(existing, verdict, spec, location, option_sets, names)
        return existing
    candidate = IngestCandidate(
        task_id=task.id,
        batch_id=task.batch_id,
        dataset_code=spec.code,
        seq=seq,
        business_key=verdict.business_key,
        source_location=location,
        source_text=source_text or None,
        raw_values=raw,
        values=verdict.values,
        field_sources=verdict.field_sources,
        conflicts=verdict.conflicts,
        errors=verdict.errors,
        warnings=verdict.warnings,
        completeness=verdict.completeness,
        triage=verdict.triage,
        duplicate_of=verdict.duplicate_of,
        target_record_id=verdict.target_record_id,
        status="pending",
    )
    session.add(candidate)
    if rule_key is not None:
        merge_index[(spec.code, rule_key)] = candidate
    elif verdict.business_key:
        merge_index[(spec.code, verdict.business_key)] = candidate
    return candidate


def _rule_key(fields: list[str] | None, values: dict[str, object]) -> str | None:
    """按用户指定字段生成合并键；任一字段为空时不合并，交给业务主键判断。"""
    if not fields:
        return None
    parts: list[str] = []
    for code in fields:
        text = unicodedata.normalize("NFKC", cell_text(values.get(code))).lower()
        text = "".join(text.split())
        if not text:
            return None
        parts.append(text)
    return "rule:" + "|".join(parts)


def _merge_target(
    merge_index: dict[tuple[str, str], IngestCandidate],
    spec: DatasetSpec,
    verdict: Verdict,
) -> IngestCandidate | None:
    if verdict.business_key is None or verdict.duplicate_of:
        return None
    return merge_index.get((spec.code, verdict.business_key))


def _merge(
    target: IngestCandidate,
    verdict: Verdict,
    spec: DatasetSpec,
    location: dict[str, object],
    option_sets: dict[str, set[str]],
    names: set[str],
) -> None:
    values = dict(target.values or {})
    sources = dict(target.field_sources or {})
    raw_values = dict(target.raw_values or {})
    conflicts = list(target.conflicts or [])
    labels = spec.field_map()
    for code, value in verdict.values.items():
        old = cell_text(values.get(code))
        new = cell_text(value)
        if not new:
            continue
        if not old:
            values[code] = value
            if code in verdict.field_sources:
                sources[code] = verdict.field_sources[code]
        elif old != new:
            conflict = {
                "field": code,
                "label": labels[code].label if code in labels else code,
                "kept": old,
                "incoming": new,
                "location": location,
            }
            if conflict not in conflicts:
                conflicts.append(conflict)
    for code, value in verdict.values.items():
        if not cell_text(raw_values.get(code)) and cell_text(value):
            raw_values[code] = value
    target.values = values
    target.field_sources = sources
    target.raw_values = raw_values
    target.conflicts = conflicts
    target.completeness = triage.completeness(spec, values)
    missing = triage.missing_required(spec, values)
    errors = _validate_lenient(spec, values, option_sets, names)[1]
    target.errors = errors
    if conflicts:
        target.warnings = _unique(list(target.warnings or []), "同批次存在字段冲突")
        target.triage = triage.TRIAGE_REVIEW
    elif target.duplicate_of:
        target.triage = triage.TRIAGE_DUPLICATE
    elif missing:
        target.triage = triage.TRIAGE_MISSING
    else:
        target.triage = triage.classify(
            spec, values, errors, sources, duplicate=None, conflict=False
        )


def _unique(items: list[str], message: str) -> list[str]:
    return items if message in items else [*items, message]


def _validate_lenient(
    spec: DatasetSpec,
    values: dict[str, object],
    option_sets: dict[str, set[str]],
    names: set[str],
) -> tuple[dict[str, object], list[str]]:
    try:
        checked, _extra = spec.validate(values, option_sets, names)
        return jsonable(checked), []
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "校验未通过"
        errors = [part for part in detail.split("；") if part and not part.endswith(_EMPTY)]
        return values, errors


async def assess(
    session: AsyncSession,
    task: IngestTask,
    spec: DatasetSpec,
    user: User,
    raw: dict[str, object],
    lookups: dict[str, dict[str, str]],
    option_sets: dict[str, set[str]],
    names: set[str],
    seen: dict[str, str] | None,
    index: KeyIndex | None = None,
    cache: LookupCache | None = None,
    *,
    source_text: str = "",
    field_sources: dict[str, dict[str, object]] | None = None,
) -> Verdict:
    _ = source_text
    data = normalize_payload(spec, raw, lookups)
    sources = dict(field_sources or {})
    enriched = await enrich(
        session,
        spec,
        user,
        data,
        sources,
        cache or LookupCache(),
        task_department_id=task.department_id,
    )
    warnings = list(enriched.warnings)
    data, errors = _validate_lenient(spec, data, option_sets, names)
    for field_spec in spec.fields:
        if (
            field_spec.default is not None
            and cell_text(data.get(field_spec.code))
            and field_spec.code not in sources
        ):
            sources[field_spec.code] = {"source": "default", "score": 0.95}
    if index is None:
        index = KeyIndex()
        await index.load(session, {spec.code})
    dup = dedupe.check(spec, data, index, user, seen)
    duplicate_of = dup.record_id if dup.kind == "conflict" else None
    target_record_id = dup.record_id if dup.kind == "editable" else None
    if dup.kind == "conflict":
        warnings.append("与已有记录重复")
    if dup.kind == "editable":
        warnings.append("将补充已有草稿")
    kind = filler_type_for(user, spec)
    if (
        kind == "teacher"
        and spec.owner_field
        and data.get(spec.owner_field) not in {None, "", user.account}
    ):
        warnings.append("无权填写")
    return Verdict(
        values=data,
        errors=errors,
        warnings=warnings,
        missing=triage.missing_required(spec, data),
        duplicate_of=duplicate_of,
        target_record_id=target_record_id,
        field_sources=sources,
        completeness=triage.completeness(spec, data),
        triage=triage.classify(
            spec,
            data,
            errors,
            sources,
            duplicate=duplicate_of,
            conflict=dup.kind == "editable",
        ),
        business_key=dedupe.business_key(spec, data),
    )


def _refresh(
    spec: DatasetSpec,
    candidate: IngestCandidate,
    values: dict[str, object],
    option_sets: dict[str, set[str]],
    names: set[str],
) -> None:
    values, errors = _validate_lenient(spec, values, option_sets, names)
    candidate.values = values
    candidate.errors = errors
    candidate.completeness = triage.completeness(spec, values)
    candidate.triage = triage.classify(
        spec,
        values,
        errors,
        candidate.field_sources,
        duplicate=candidate.duplicate_of,
        conflict=bool(candidate.conflicts),
    )


def _file_sources(
    plan: StructurePlan, sheet_plan: object, raw: dict[str, object]
) -> dict[str, dict[str, object]]:
    from app.ingestion.plan import SheetPlan

    score = 0.85 if plan.source == "llm" else 0.95
    sources: dict[str, dict[str, object]] = {}
    if isinstance(sheet_plan, SheetPlan):
        for column in sheet_plan.columns:
            targets = [column.field] if column.field else list(column.fields or [])
            for target in targets:
                if cell_text(raw.get(target)):
                    sources[target] = {"source": "file", "score": score}
    for code, value in raw.items():
        if cell_text(value) and code not in sources:
            sources[code] = {"source": "file", "score": score}
    return sources


async def _merge_index(
    session: AsyncSession, task: IngestTask, dataset_codes: set[str]
) -> dict[tuple[str, str], IngestCandidate]:
    query = select(IngestCandidate).where(
        IngestCandidate.status == "pending",
        IngestCandidate.dataset_code.in_(dataset_codes),
    )
    if task.batch_id:
        query = query.where(IngestCandidate.batch_id == task.batch_id)
    else:
        query = query.where(IngestCandidate.task_id == task.id)
    rows = (await session.scalars(query.order_by(IngestCandidate.seq))).all()
    found: dict[tuple[str, str], IngestCandidate] = {}
    for row in rows:
        if row.business_key:
            found.setdefault((row.dataset_code, row.business_key), row)
    return found


def _parse(path: str, content: bytes) -> ParsedDocument:
    suffix = Path(path).suffix.lower()
    if suffix == ".xlsx":
        _guard_raw_size(content)
        return parse_xlsx(content)
    if suffix == ".xls":
        return parse_xls(content)
    if suffix == ".csv":
        return parse_csv(content)
    if suffix == ".pdf":
        return parse_pdf(content)
    if suffix == ".docx":
        return parse_docx(content)
    raise IngestFailure("unsupported", "不支持的文件类型")


def _guard_raw_size(content: bytes) -> None:
    """加载工作簿前先按 dimension 估算，避免超大表把内存吃满再报错。"""
    estimated = estimate_xlsx_cells(content)
    ceiling = settings.ingest_max_cells * 4
    if estimated is not None and estimated > ceiling:
        raise IngestFailure(
            "too_large",
            f"文件数据量过大：表格约有 {estimated:,} 个单元格，超过上限 {ceiling:,}。"
            "请拆分文件后重新上传，或调大后端 INGEST_MAX_CELLS。",
        )


def _guard_document(path: str, document: ParsedDocument) -> None:
    if document.page_count > settings.ingest_max_pdf_pages:
        raise IngestFailure("too_large", f"PDF 不能超过 {settings.ingest_max_pdf_pages} 页")
    limit = settings.ingest_max_cells
    if document.sheets:
        filled = document.filled_cells
        if filled > limit:
            raise IngestFailure(
                "too_large",
                f"文件数据量过大：约 {filled:,} 个非空单元格，超过上限 {limit:,}。"
                "请拆分文件后重新上传，或调大后端 INGEST_MAX_CELLS。",
            )
    elif document.cell_count > limit:
        raise IngestFailure(
            "too_large",
            f"文件数据量过大：约 {document.cell_count:,} 个单元格，"
            f"超过上限 {limit:,}。请拆分文件后重新上传。",
        )
    if Path(path).suffix.lower() != ".pdf" or document.sheets:
        return
    if document.page_count and document.text_chars / document.page_count < 20:
        raise IngestFailure("scan_unsupported", _SCAN)


def _lookups(found: dict[str, list[DictOption]]) -> dict[str, dict[str, str]]:
    lookups: dict[str, dict[str, str]] = {}
    for code, items in found.items():
        choice = {item.label: item.value for item in items}
        choice.update({item.value: item.value for item in items})
        lookups[code] = choice
    return lookups


def _guide_options(found: dict[str, list[DictOption]]) -> dict[str, list[tuple[str, str]]]:
    return {code: [(item.value, item.label) for item in items] for code, items in found.items()}


def _prompt_version(plan: StructurePlan | None, document: ParsedDocument) -> str:
    source = plan.source if plan else "text"
    if document.blocks and plan:
        return f"{source}+{RECORD_VERSION}"
    if document.blocks:
        return RECORD_VERSION
    return source


def _fail(task: IngestTask, code: str, message: str) -> None:
    task.status = "failed"
    task.error_code = code
    task.error_message = message[:500]
    task.finished_at = _now()
    task.progress = 100
    logger.info("ingest failed task=%s code=%s", task.id, code)
