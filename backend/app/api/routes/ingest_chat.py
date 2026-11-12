"""多轮补齐：轮次报告、下一步建议、补充模板、一句话批量动作。"""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.ai.calls import BudgetExceeded, Caller, OutputInvalid
from app.ai.client import HttpxLLMClient, LLMClient, ModelUnavailable
from app.ai.extract import parse_action
from app.api.deps import DbSession
from app.api.routes.ingestion import (
    Parser,
    _batch_for,
    _context,
    _reassess,
)
from app.core.config import resolved_ai, settings
from app.datasets.registry import get_dataset
from app.ingestion import actions, priority, rounds, supplement, template_file
from app.ingestion.normalize import cell_text
from app.models.ingestion import IngestAction, IngestBatch, IngestCandidate, IngestRound, IngestTask
from app.schemas.ingestion import ActionRead, MessageResult, MessageWrite, NextRead, RoundRead
from app.services.staff import load_dict_options

router = APIRouter(tags=["文件解析"])
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _now() -> datetime:
    return datetime.now(UTC)


def _client() -> LLMClient | None:
    _provider, _base, key, _model = resolved_ai()
    return HttpxLLMClient() if key else None


def _round(row: IngestRound) -> RoundRead:
    return RoundRead(
        id=row.id,
        seq=row.seq,
        trigger=row.trigger,
        task_id=row.task_id,
        action_id=row.action_id,
        report=row.report,
        created_at=row.created_at,
    )


def _action(row: IngestAction) -> ActionRead:
    return ActionRead(
        id=row.id,
        batch_id=row.batch_id,
        message=row.message,
        action=row.action,
        preview=row.preview or {},
        status=row.status,
        created_at=row.created_at,
        applied_at=row.applied_at,
    )


@router.get("/api/ingestion/batches/{batch_id}/rounds", response_model=list[RoundRead])
async def list_rounds(batch_id: str, session: DbSession, user: Parser) -> list[RoundRead]:
    batch = await _batch_for(session, user, batch_id)
    rows = await session.scalars(
        select(IngestRound).where(IngestRound.batch_id == batch.id).order_by(IngestRound.seq)
    )
    return [_round(row) for row in rows]


@router.get("/api/ingestion/batches/{batch_id}/next", response_model=NextRead)
async def next_step(batch_id: str, session: DbSession, user: Parser) -> NextRead:
    batch = await _batch_for(session, user, batch_id)
    return NextRead.model_validate((await rounds.overview(session, batch)).as_dict())


@router.get("/api/ingestion/batches/{batch_id}/actions", response_model=list[ActionRead])
async def list_actions(batch_id: str, session: DbSession, user: Parser) -> list[ActionRead]:
    batch = await _batch_for(session, user, batch_id)
    rows = await session.scalars(
        select(IngestAction)
        .where(IngestAction.batch_id == batch.id)
        .order_by(IngestAction.created_at)
    )
    return [_action(row) for row in rows]


@router.get("/api/ingestion/batches/{batch_id}/supplement-template")
async def supplement_template(
    batch_id: str,
    dataset_code: str,
    session: DbSession,
    user: Parser,
    fields: str = "",
) -> Response:
    batch = await _batch_for(session, user, batch_id)
    if dataset_code not in set(batch.dataset_codes or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该数据表不在本批次内")
    spec = get_dataset(dataset_code)
    known = spec.field_map()
    rows = [
        row for row in await rounds.pending_rows(session, batch.id) if row.dataset_code == spec.code
    ]
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="本批次还没有该数据表的记录")
    candidates = {row.id: dict(row.values or {}) for row in rows}
    key = supplement.choose_key(set(known), candidates, supplement.key_options(spec))
    if key is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="现有记录缺少能唯一识别的字段，请先上传含主键的文件",
        )
    codes = [code for code in fields.split(",") if code in known]
    if not codes:
        codes = [gap.code for gap in priority.gaps_for(spec, list(candidates.values()))]
    codes = [code for code in dict.fromkeys(codes) if code not in key]
    codes = codes[: settings.supplement_template_fields]
    if not codes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="没有需要补充的字段")
    targets = [
        values
        for values in candidates.values()
        if supplement.key_text(values, key)
        and any(not cell_text(values.get(code)) for code in codes)
    ]
    found, _option_sets = await load_dict_options(session)
    options = {code: [(item.value, item.label) for item in items] for code, items in found.items()}
    content = template_file.build(spec, batch.id, key, codes, targets, options)
    name = quote(f"{spec.name}-补充模板.xlsx")
    return Response(
        content=content,
        media_type=_XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )


async def _accounting_task(session: DbSession, batch: IngestBatch) -> IngestTask | None:
    """批量动作不属于任何文件任务，模型用量记到批次最近一个任务上。"""
    task: IngestTask | None = await session.scalar(
        select(IngestTask)
        .where(IngestTask.batch_id == batch.id)
        .order_by(IngestTask.created_at.desc())
        .limit(1)
    )
    return task


@router.post("/api/ingestion/batches/{batch_id}/messages", response_model=MessageResult)
async def post_message(
    batch_id: str, body: MessageWrite, session: DbSession, user: Parser
) -> MessageResult:
    """把一句话翻译成待确认的批量动作。只生成预览，不改任何候选。"""
    batch = await _batch_for(session, user, batch_id)
    used = int(
        await session.scalar(
            select(func.count()).select_from(IngestAction).where(IngestAction.batch_id == batch.id)
        )
        or 0
    )
    if used >= settings.ai_batch_max_action_calls:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="本批次的对话次数已用完")
    task = await _accounting_task(session, batch)
    if task is None:
        return MessageResult(reply="请先上传第一份文件，识别出记录后再用一句话批量补充。")
    client = _client()
    if client is None:
        return MessageResult(reply="模型服务未配置，请使用补充模板或在表格中批量修改。")
    view = await rounds.overview(session, batch)
    codes = list(dict.fromkeys([*(batch.dataset_codes or []), *view.totals]))
    specs = {code: get_dataset(code) for code in codes}
    found, _option_sets = await load_dict_options(session)
    options = {code: [(item.value, item.label) for item in items] for code, items in found.items()}
    context = actions.context_text(
        list(specs.values()), view.totals, view.gaps, options, view.conflicts
    )
    caller = Caller(session, task, client, budget=task.llm_calls + 1, cache_enabled=False)
    try:
        proposed = await parse_action(caller, context, body.text.strip())
    except (ModelUnavailable, BudgetExceeded):
        return MessageResult(reply="模型服务暂不可用，请稍后再试，或使用补充模板。")
    except OutputInvalid:
        return MessageResult(reply="没能理解这句话，请换个说法，例如“这些课程都不是校企合作开发”。")
    default = body.dataset_code or (codes[0] if len(codes) == 1 else None)
    ctx = await _context(session, set(specs))
    try:
        action = actions.validate(proposed, specs, ctx.lookups, default)
    except actions.ActionInvalid as exc:
        await session.commit()
        return MessageResult(reply=str(exc))
    spec = specs[action.dataset_code]
    names = {code: {value: label for value, label in items} for code, items in options.items()}
    rows = actions.targets(spec, await rounds.pending_rows(session, batch.id), action)
    shown = actions.preview(spec, action, rows, names)
    row = IngestAction(
        batch_id=batch.id,
        message=body.text.strip()[:500],
        action=action.as_dict(),
        preview=shown,
        status="proposed",
        created_by=user.id,
        created_at=_now(),
    )
    session.add(row)
    await session.commit()
    if action.kind == "skip_field":
        reply = f"将{shown['summary']}。确认后生效。"
    elif rows:
        reply = f"将{shown['summary']}，共影响 {len(rows)} 条记录。请确认后执行。"
    else:
        reply = f"按“{shown['summary']}”没有找到需要修改的记录。"
    return MessageResult(reply=reply, action=_action(row))


async def _action_for(
    session: DbSession, user: Parser, action_id: str
) -> tuple[IngestAction, IngestBatch]:
    row = await session.get(IngestAction, action_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="操作不存在")
    batch = await _batch_for(session, user, row.batch_id)
    return row, batch


@router.post("/api/ingestion/actions/{action_id}/reject", response_model=ActionRead)
async def reject_action(action_id: str, session: DbSession, user: Parser) -> ActionRead:
    row, _batch = await _action_for(session, user, action_id)
    if row.status == "proposed":
        row.status = "rejected"
        await session.commit()
    return _action(row)


def _keep_conflicts(row: IngestCandidate, conflicts: list[dict[str, object]]) -> None:
    """重新校验会清空冲突；未处理的冲突要保留下来。"""
    if not conflicts:
        return
    row.conflicts = conflicts
    if "同批次存在字段冲突" not in (row.warnings or []):
        row.warnings = [*(row.warnings or []), "同批次存在字段冲突"]
    if row.triage != "duplicate":
        row.triage = "review"


@router.post("/api/ingestion/actions/{action_id}/apply")
async def apply_action(action_id: str, session: DbSession, user: Parser) -> dict[str, object]:
    row, batch = await _action_for(session, user, action_id)
    if row.status != "proposed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该操作已处理")
    if row.created_at + timedelta(minutes=settings.action_proposal_ttl_minutes) < _now():
        row.status = "expired"
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="操作已过期，请重新描述")
    action = actions.Action.from_dict(row.action)
    spec = get_dataset(action.dataset_code)
    pending = await rounds.pending_rows(session, batch.id)
    rows = actions.targets(spec, pending, action)
    expected = int((row.preview or {}).get("count") or 0)  # type: ignore[call-overload]
    if abs(len(rows) - expected) > max(1, expected // 10):
        found, _option_sets = await load_dict_options(session)
        names = {code: {item.value: item.label for item in items} for code, items in found.items()}
        row.preview = actions.preview(spec, action, rows, names)
        await session.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"影响范围已从 {expected} 条变为 {len(rows)} 条，请重新确认",
        )
    before = await rounds.snapshot(session, batch.id)
    ctx = await _context(session, {spec.code})
    source = {"source": "bulk", "score": 1.0, "ref": {"action": row.id}}
    for candidate in rows:
        values = dict(candidate.values or {})
        conflicts = list(candidate.conflicts or [])
        if action.kind == "bulk_set" and action.field:
            values[action.field] = action.value
        elif action.kind == "resolve_conflict":
            remaining = []
            for conflict in conflicts:
                if action.field and conflict.get("field") != action.field:
                    remaining.append(conflict)
                    continue
                if action.value == "incoming":
                    values[str(conflict.get("field"))] = conflict.get("incoming")
            conflicts = remaining
        else:
            continue
        await _reassess(session, candidate, values, source=source, ctx=ctx)
        _keep_conflicts(candidate, conflicts)
    row.status = "applied"
    row.applied_at = _now()
    await session.flush()
    report = await rounds.record(
        session,
        batch.id,
        trigger="action",
        before=before,
        user_id=user.id,
        dataset_code=action.dataset_code,
        action_id=row.id,
        extra={"message": row.message, "summary": (row.preview or {}).get("summary")},
    )
    batch.updated_at = _now()
    await session.commit()
    return {
        "action": _action(row).model_dump(mode="json"),
        "round": _round(report).model_dump(mode="json") if report else None,
    }
