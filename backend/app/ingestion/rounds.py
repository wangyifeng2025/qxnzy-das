"""轮次报告：对比本轮前后的候选，告诉用户填进了什么、还缺什么、下一步做什么。

报告完全由程序统计生成，不调用模型。文件任务和批量动作共用同一套对比逻辑。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.datasets.registry import get_dataset
from app.datasets.spec import DatasetSpec
from app.ingestion import priority, triage
from app.ingestion.normalize import cell_text
from app.models.ingestion import (
    IngestAction,
    IngestBatch,
    IngestCandidate,
    IngestFile,
    IngestRound,
    IngestTask,
)
from app.services.staff import load_dict_options

logger = logging.getLogger(__name__)
_AUTO_SOURCES = {"lookup", "derive", "join", "default"}
_GAP_LIMIT = 10


@dataclass(frozen=True)
class RowState:
    dataset_code: str
    filled: frozenset[str]
    missing: frozenset[str]
    conflicts: int
    completeness: int
    triage: str


Snapshot = dict[str, RowState]


def _now() -> datetime:
    return datetime.now(UTC)


async def pending_rows(session: AsyncSession, batch_id: str) -> list[IngestCandidate]:
    return list(
        (
            await session.scalars(
                select(IngestCandidate)
                .where(
                    IngestCandidate.batch_id == batch_id,
                    IngestCandidate.status == "pending",
                    IngestCandidate.record_id.is_(None),
                )
                .order_by(IngestCandidate.seq)
            )
        ).all()
    )


def _state(spec: DatasetSpec, row: IngestCandidate) -> RowState:
    values = row.values or {}
    return RowState(
        dataset_code=row.dataset_code,
        filled=frozenset(code for code, value in values.items() if cell_text(value)),
        missing=frozenset(triage.missing_required(spec, values)),
        conflicts=len(row.conflicts or []),
        completeness=row.completeness,
        triage=row.triage,
    )


async def snapshot(session: AsyncSession, batch_id: str) -> Snapshot:
    await session.flush()
    return {
        row.id: _state(get_dataset(row.dataset_code), row)
        for row in await pending_rows(session, batch_id)
    }


async def skipped_fields(session: AsyncSession, batch_id: str) -> dict[str, set[str]]:
    """用户说过“这个字段先不填”的，不再出现在建议里。"""
    rows = await session.scalars(
        select(IngestAction).where(
            IngestAction.batch_id == batch_id, IngestAction.status == "applied"
        )
    )
    found: dict[str, set[str]] = {}
    for row in rows:
        action = row.action or {}
        if action.get("action") == "skip_field":
            found.setdefault(str(action.get("dataset_code")), set()).add(str(action.get("field")))
    return found


@dataclass
class Overview:
    order: list[str]
    totals: dict[str, int]
    ready: int
    conflicts: int
    gaps: list[dict[str, object]]
    next: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "totals": self.totals,
            "ready": self.ready,
            "conflicts": self.conflicts,
            "gaps": self.gaps,
            "next": self.next,
        }


async def overview(session: AsyncSession, batch: IngestBatch) -> Overview:
    """当前批次的缺口（按优先级）和下一步建议。"""
    rows = await pending_rows(session, batch.id)
    codes = list(dict.fromkeys([*(batch.dataset_codes or []), *(row.dataset_code for row in rows)]))
    specs = [get_dataset(code) for code in codes]
    found, _option_sets = await load_dict_options(session)
    option_counts = {code: len(items) for code, items in found.items()}
    skipped = await skipped_fields(session, batch.id)
    gaps: dict[str, list[priority.Gap]] = {}
    totals: dict[str, int] = {}
    ready = 0
    conflicts = 0
    for spec in specs:
        values = [row.values or {} for row in rows if row.dataset_code == spec.code]
        totals[spec.code] = len(values)
        gaps[spec.code] = priority.gaps_for(
            spec, values, skipped=skipped.get(spec.code), option_counts=option_counts
        )
    for row in rows:
        if row.triage == triage.TRIAGE_AUTO:
            ready += 1
        if row.conflicts:
            conflicts += 1
    order = priority.dataset_order(specs)
    blocking = await _blocking_task(session, batch.id)
    suggestion = blocking or priority.next_step(
        order,
        gaps,
        names={spec.code: spec.name for spec in specs},
        totals=totals,
        conflicts=conflicts,
        ready=ready,
        template_fields=settings.supplement_template_fields,
    )
    return Overview(
        order=order,
        totals=totals,
        ready=ready,
        conflicts=conflicts,
        gaps=[gap.as_dict() for code in order for gap in gaps.get(code, [])],
        next=suggestion,
    )


async def _blocking_task(session: AsyncSession, batch_id: str) -> dict[str, object] | None:
    """有文件等着确认读取方式或还在解析时，先处理它，而不是建议上传新文件。"""
    rows = (
        await session.execute(
            select(
                IngestTask.id, IngestTask.status, IngestTask.dataset_code, IngestFile.original_name
            )
            .join(IngestFile, IngestFile.task_id == IngestTask.id, isouter=True)
            .where(
                IngestTask.batch_id == batch_id,
                IngestTask.status.in_(["awaiting_plan", "queued", "parsing", "extracting"]),
            )
            .order_by(IngestTask.created_at)
        )
    ).all()
    for task_id, status, dataset_code, name in rows:
        if status == "awaiting_plan":
            return {
                "kind": "plan",
                "task_id": task_id,
                "dataset_code": dataset_code,
                "fields": [],
                "message": f"文件「{name or '未命名'}」的读取方式需要你确认后才会继续。",
            }
    if rows:
        return {
            "kind": "wait",
            "task_id": rows[0][0],
            "dataset_code": rows[0][2],
            "fields": [],
            "message": f"正在处理 {len(rows)} 个文件，完成后会告诉你填进了什么、还缺什么。",
        }
    return None


def _average(states: list[RowState]) -> int:
    if not states:
        return 0
    return round(sum(state.completeness for state in states) / len(states))


def compare(
    before: Snapshot,
    rows: list[IngestCandidate],
    dataset_code: str | None,
) -> dict[str, object]:
    """本轮前后对比：新增、被补充的记录数，按字段统计填入与自动带出。"""
    after: Snapshot = {}
    filled: dict[str, int] = {}
    auto: dict[str, tuple[int, str]] = {}
    matched = 0
    created = 0
    new_conflicts = 0
    for row in rows:
        spec = get_dataset(row.dataset_code)
        state = _state(spec, row)
        after[row.id] = state
        if dataset_code and row.dataset_code != dataset_code:
            continue
        old = before.get(row.id)
        if old is None:
            created += 1
            continue
        gained = state.filled - old.filled
        if gained or state.conflicts != old.conflicts:
            matched += 1
        new_conflicts += max(0, state.conflicts - old.conflicts)
        sources = row.field_sources or {}
        for code in gained:
            source = sources.get(code)
            kind = str(source.get("source")) if isinstance(source, dict) else ""
            if kind in _AUTO_SOURCES:
                count, _via = auto.get(code, (0, kind))
                auto[code] = (count + 1, kind)
            else:
                filled[code] = filled.get(code, 0) + 1

    def scoped(snap: Snapshot) -> list[RowState]:
        return [
            state
            for state in snap.values()
            if not dataset_code or state.dataset_code == dataset_code
        ]

    labels = get_dataset(dataset_code).field_map() if dataset_code else {}

    def label(code: str) -> str:
        item = labels.get(code)
        return item.label if item else code

    current = scoped(after)
    return {
        "matched": matched,
        "created": created,
        "filled": [
            {"code": code, "label": label(code), "count": count}
            for code, count in sorted(filled.items(), key=lambda item: -item[1])
        ],
        "auto_filled": [
            {"code": code, "label": label(code), "count": count, "via": via}
            for code, (count, via) in sorted(auto.items(), key=lambda item: -item[1][0])
        ],
        "new_conflicts": new_conflicts,
        "completeness_before": _average(scoped(before)),
        "completeness_after": _average(current),
        "total": len(current),
        "ready": sum(1 for state in current if state.triage == triage.TRIAGE_AUTO),
    }


def render(report: dict[str, object]) -> list[str]:
    """把报告转成几句话，前端直接展示。"""
    lines: list[str] = []
    detail = report.get("supplement")
    if report.get("status") == "awaiting_plan":
        if isinstance(detail, dict):
            lines.append(
                f"按「{'+'.join(detail.get('key_labels') or [])}」只对上 {detail.get('matched')}"
                f"/{detail.get('rows')} 行，冲突 {detail.get('conflicts')} 行，"
                "未达到自动补齐条件，请确认后再补齐。"
            )
        else:
            lines.append("这份文件的读取方式需要你确认后才会继续。")
        return lines
    if isinstance(detail, dict):
        key = "+".join(detail.get("key_labels") or [])
        matched = report.get("matched")
        lines.append(f"按「{key}」对上已有记录 {matched} 条（文件共 {detail.get('rows')} 行）。")
    elif report.get("trigger") == "file":
        parts = [f"新识别 {report.get('created')} 条记录"]
        if report.get("matched"):
            parts.append(f"与已有记录合并 {report.get('matched')} 条")
        lines.append("，".join(parts) + "。")
    elif report.get("matched"):
        lines.append(f"已修改 {report.get('matched')} 条记录。")
    filled = report.get("filled") or []
    if isinstance(filled, list) and filled:
        lines.append(
            "已填入：" + "、".join(f"{item['label']} {item['count']} 条" for item in filled[:8])
        )
    auto = report.get("auto_filled") or []
    if isinstance(auto, list) and auto:
        lines.append(
            "自动带出：" + "、".join(f"{item['label']} {item['count']} 条" for item in auto[:8])
        )
    if report.get("new_conflicts"):
        lines.append(f"新增 {report.get('new_conflicts')} 处取值冲突，未覆盖原值，需要你确认。")
    if isinstance(detail, dict):
        if detail.get("extra"):
            samples = "、".join(str(item) for item in detail.get("extra_samples") or [])
            lines.append(
                f"文件中多出 {detail.get('extra')} 条记录（如 {samples}），未加入本批次；"
                "如需新增，请勾选“作为新数据”重新上传。"
            )
        if detail.get("ambiguous"):
            lines.append(f"有 {detail.get('ambiguous')} 行在文件中重复且取值不同，已跳过。")
        if detail.get("no_key"):
            lines.append(f"有 {detail.get('no_key')} 行缺少匹配字段，已跳过。")
    lines.append(
        f"完成度 {report.get('completeness_before')}% → {report.get('completeness_after')}%，"
        f"{report.get('ready')}/{report.get('total')} 条可直接确认。"
    )
    return lines


async def record(
    session: AsyncSession,
    batch_id: str,
    *,
    trigger: str,
    before: Snapshot,
    user_id: int,
    dataset_code: str | None,
    task_id: str | None = None,
    action_id: str | None = None,
    extra: dict[str, object] | None = None,
) -> IngestRound | None:
    batch = await session.get(IngestBatch, batch_id)
    if batch is None:
        return None
    rows = await pending_rows(session, batch_id)
    report: dict[str, object] = {
        "trigger": trigger,
        "task_id": task_id,
        "action_id": action_id,
        "dataset_code": dataset_code,
        **(extra or {}),
    }
    report.update(compare(before, rows, dataset_code))
    view = await overview(session, batch)
    report["gaps"] = view.gaps[:_GAP_LIMIT]
    report["next"] = view.next
    report["lines"] = render(report)
    for _attempt in range(3):
        seq = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(IngestRound.seq), 0)).where(
                        IngestRound.batch_id == batch_id
                    )
                )
                or 0
            )
            + 1
        )
        report["seq"] = seq
        row = IngestRound(
            batch_id=batch_id,
            seq=seq,
            trigger=trigger,
            task_id=task_id,
            action_id=action_id,
            report=dict(report),
            created_by=user_id,
            created_at=_now(),
        )
        try:
            async with session.begin_nested():
                session.add(row)
            return row
        except IntegrityError:
            logger.info("round seq collision batch=%s seq=%s", batch_id, seq)
    return None
