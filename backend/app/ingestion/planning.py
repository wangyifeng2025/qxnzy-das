"""结构计划的选择、校验与试跑。

顺序：用户已确认 → 模板记忆 → 精确匹配 → 模型规划 → 用户确认。
模型只在结构看不懂时参与，且输出必须先通过校验和试跑才允许自动执行。
"""

import hashlib
import logging
from typing import TYPE_CHECKING

from app.datasets.spec import DatasetSpec
from app.ingestion.execute import build_records
from app.ingestion.mapping import exact_plan
from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.plan import DryRun, PlanGap, SheetPlan, StructurePlan, mapped_fields
from app.ingestion.profile import DocumentProfile, SheetProfile, normalize_header

if TYPE_CHECKING:
    from app.ai.calls import Caller
    from app.models.system import User

logger = logging.getLogger(__name__)

AUTO_CONFIDENCE = 0.8
MAX_ERROR_RATE = 0.1


class PlanInvalid(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("；".join(errors))


def document_signature(profile: DocumentProfile) -> str:
    joined = "|".join(sorted(profile.signatures))
    return hashlib.sha256(joined.encode()).hexdigest()[:32]


def exact_for(
    specs: dict[str, DatasetSpec],
    profile: DocumentProfile,
    aliases: dict[str, dict[str, str]],
) -> StructurePlan | None:
    """每个目标数据集都要能找到完整表头，否则交给模型。"""
    sheets = [sheet for sheet in profile.sheets if not sheet.skip_reason]
    assigned: dict[str, SheetProfile] = {}
    used: set[str] = set()
    for code, spec in specs.items():
        candidates = [sheet for sheet in sheets if sheet.sheet not in used]
        scored = sorted(
            candidates,
            key=lambda sheet: _match_score(spec, sheet, aliases.get(code, {})),
            reverse=True,
        )
        for sheet in scored:
            if exact_plan(spec, sheet, aliases.get(code, {})) is not None:
                assigned[code] = sheet
                used.add(sheet.sheet)
                break
        else:
            return None
    sheets_plan: list[SheetPlan] = []
    for code, sheet in assigned.items():
        plan = exact_plan(specs[code], sheet, aliases.get(code, {}))
        if plan is None:
            return None
        sheets_plan.append(plan)
    return StructurePlan(sheets=sheets_plan, source="exact", confidence=1)


def _match_score(spec: DatasetSpec, sheet: SheetProfile, extra: dict[str, str]) -> int:
    from app.ingestion.mapping import match_header

    return sum(1 for header in sheet.headers if match_header(spec, header, extra))


def validate_plan(
    plan: StructurePlan,
    profile: DocumentProfile,
    specs: dict[str, DatasetSpec],
) -> StructurePlan:
    errors: list[str] = []
    normalized: list[SheetPlan] = []
    seen_sheets: set[str] = set()
    mains = 0
    inherited = _reference_datasets(plan)
    for sheet_plan in plan.sheets:
        if sheet_plan.role == "reference" and not sheet_plan.dataset_code:
            sheet_plan = sheet_plan.model_copy(
                update={"dataset_code": inherited.get(sheet_plan.sheet)}
            )
        known = profile.get(sheet_plan.sheet)
        if known is None:
            errors.append(f"工作表「{sheet_plan.sheet}」不存在")
            continue
        if sheet_plan.sheet in seen_sheets:
            errors.append(f"工作表「{sheet_plan.sheet}」重复出现")
        seen_sheets.add(sheet_plan.sheet)
        if sheet_plan.role == "ignore":
            normalized.append(sheet_plan)
            continue
        if sheet_plan.role == "main":
            mains += 1
        spec = specs.get(sheet_plan.dataset_code or "")
        if spec is None:
            errors.append(f"工作表「{sheet_plan.sheet}」未指定有效数据集")
            continue
        if sheet_plan.header_pattern == "columnar":
            sheet_plan = sheet_plan.model_copy(update={"header_rows": [1], "data_start": 2})
        sheet_plan = _drop_repeated_targets(sheet_plan)
        if sheet_plan.dedupe_by:
            known_fields = spec.field_map()
            sheet_plan = sheet_plan.model_copy(
                update={
                    "dedupe_by": [
                        code for code in dict.fromkeys(sheet_plan.dedupe_by) if code in known_fields
                    ]
                }
            )
        _check_ranges(sheet_plan, known, errors)
        _check_columns(sheet_plan, known, spec, errors)
        _check_modes(sheet_plan, spec, errors)
        normalized.append(sheet_plan)
    plan = plan.model_copy(update={"sheets": normalized})
    if mains == 0 and any(not sheet.skip_reason for sheet in profile.sheets):
        errors.append("没有任何工作表被指定为数据表")
    _check_groups(plan, errors)
    _check_joins(plan, specs, errors)
    if errors:
        raise PlanInvalid(errors)
    return plan


def _drop_repeated_targets(sheet_plan: SheetPlan) -> SheetPlan:
    """同一字段被多列直接映射时只保留第一列。

    导出表常有重名列（例如两列“课程号”），模型会把它们都映射到同一字段；
    执行时按表头顺序取值，第一列就是表头对应的那一列，后面的列改为忽略。
    """
    seen: set[str] = set()
    columns = []
    dropped: list[str] = []
    for column in sheet_plan.columns:
        if column.field and column.transform == "direct" and not column.headers:
            if column.field in seen:
                dropped.append(f"{column.header}→{column.field}")
                column = column.model_copy(update={"field": None})
            else:
                seen.add(column.field)
        columns.append(column)
    if not dropped:
        return sheet_plan
    logger.info("plan sheet=%s drop repeated mappings %s", sheet_plan.sheet, dropped)
    return sheet_plan.model_copy(update={"columns": columns})


def _reference_datasets(plan: StructurePlan) -> dict[str, str]:
    """参考表只用来补主表字段，列映射按主表的数据集校验。"""
    mains = {
        sheet.sheet: sheet.dataset_code
        for sheet in plan.sheets
        if sheet.role == "main" and sheet.dataset_code
    }
    found: dict[str, str] = {}
    for join in plan.joins:
        code = mains.get(join.main_sheet)
        if code:
            found.setdefault(join.reference_sheet, code)
    return found


def _check_ranges(sheet_plan: SheetPlan, known: SheetProfile, errors: list[str]) -> None:
    header_rows = list(sheet_plan.header_rows)
    name = sheet_plan.sheet
    if not header_rows:
        errors.append(f"「{name}」没有表头行")
        return
    if header_rows != sorted(header_rows):
        errors.append(f"「{name}」表头行须从小到大")
    if header_rows[0] < 1 or header_rows[-1] > known.rows:
        errors.append(f"「{name}」表头行超出范围")
    if sheet_plan.data_start <= max(header_rows):
        errors.append(f"「{name}」数据起始行须在表头之后")
    if sheet_plan.data_start > known.rows:
        errors.append(f"「{name}」没有数据行")
    if sheet_plan.data_end is not None and (
        sheet_plan.data_end < sheet_plan.data_start or sheet_plan.data_end > known.rows
    ):
        errors.append(f"「{name}」数据结束行超出范围")


def _check_columns(
    sheet_plan: SheetPlan, known: SheetProfile, spec: DatasetSpec, errors: list[str]
) -> None:
    name = sheet_plan.sheet
    columns = list(sheet_plan.columns)
    if not columns:
        errors.append(f"「{name}」没有列对应关系")
        return
    known_headers = {normalize_header(header) for header in known.headers if header}
    for text in known.header_texts:
        known_headers.update(normalize_header(item) for item in text if item)
    mapped: set[str] = set()
    fields = spec.field_map()
    for column in columns:
        transform = column.transform
        if transform == "narrative":
            if column.field:
                errors.append(f"「{name}」描述列不能映射字段")
            continue
        if transform in {"split_date_range", "split_name_id"}:
            if not column.fields or len(column.fields) < 2:
                errors.append(f"「{name}」拆分列须指定两个字段")
                continue
            targets = list(column.fields)
        elif transform == "concat_date":
            if not column.field or not column.headers or len(column.headers) < 2:
                errors.append(f"「{name}」合并日期列须指定多个表头和字段")
                continue
            targets = [column.field]
        else:
            targets = [column.field] if column.field else []
        for target in targets:
            if target not in fields:
                errors.append(f"「{name}」字段 {target} 不属于 {spec.name}")
            elif target in mapped:
                errors.append(f"「{name}」字段 {target} 被重复映射")
            else:
                mapped.add(target)
        if transform == "repeat_group" and column.group is None:
            errors.append(f"「{name}」重复组列须指定分组编号")
        if sheet_plan.header_pattern == "normal":
            for header in [column.header, *(column.headers or [])]:
                if header and normalize_header(header) not in known_headers:
                    errors.append(f"「{name}」表头「{header}」不存在于该工作表")
                    break


def _check_modes(sheet_plan: SheetPlan, spec: DatasetSpec, errors: list[str]) -> None:
    if sheet_plan.row_mode != "grouped":
        return
    fields = spec.field_map()
    if not sheet_plan.group_key:
        errors.append(f"「{sheet_plan.sheet}」按主键分组时必须指定 group_key")
    for field in [*sheet_plan.group_key, *sheet_plan.multi_value_fields]:
        if field not in fields:
            errors.append(f"「{sheet_plan.sheet}」分组字段 {field} 不属于 {spec.name}")


def _check_groups(plan: StructurePlan, errors: list[str]) -> None:
    names = {sheet.sheet for sheet in plan.sheets}
    seen: set[str] = set()
    for group in plan.merge_sheets:
        if len(group) < 2:
            errors.append("多表拼接至少需要两个工作表")
        for name in group:
            if name not in names:
                errors.append(f"拼接工作表「{name}」不在计划中")
            if name in seen:
                errors.append(f"工作表「{name}」重复出现在拼接组")
            seen.add(name)


def _check_joins(plan: StructurePlan, specs: dict[str, DatasetSpec], errors: list[str]) -> None:
    by_name = {sheet.sheet: sheet for sheet in plan.sheets}
    for join in plan.joins:
        reference = by_name.get(join.reference_sheet)
        main = by_name.get(join.main_sheet)
        if reference is None or main is None:
            errors.append("跨表关联引用了不存在的工作表")
            continue
        if not join.on:
            errors.append("跨表关联须指定 on 字段")
        spec = specs.get(main.dataset_code or "")
        if spec is None:
            continue
        for field in [*join.on, *join.fill]:
            if field not in spec.field_map():
                errors.append(f"跨表关联字段 {field} 不属于 {spec.name}")


def dry_run(
    document: ParsedDocument,
    plan: StructurePlan,
    specs: dict[str, DatasetSpec],
    *,
    limit: int = 50,
) -> DryRun:
    execution = build_records(document, plan, limit=limit)
    by_dataset: dict[str, list[dict[str, object]]] = {}
    for record in execution.records:
        by_dataset.setdefault(record.dataset_code, []).append(record.raw)
    gaps: list[PlanGap] = []
    conditional: list[PlanGap] = []
    total = 0
    covered = 0
    missing_records = 0
    duplicate_keys = 0
    for code, spec in specs.items():
        rows = by_dataset.get(code, [])
        planned: set[str] = set()
        for sheet in plan.sheets:
            if sheet.dataset_code == code and sheet.role == "main":
                planned |= mapped_fields(sheet)
        fillable = planned | spec.enrich_targets()
        for rule in spec.derives:
            fillable.update(rule.fill)
        required = spec.required_codes()
        for field in required:
            if field not in fillable:
                gaps.append(
                    PlanGap(code=field, label=spec.field_map()[field].label, reason="no_column")
                )
        for field in spec.conditional_fields():
            if field.code not in fillable:
                conditional.append(PlanGap(code=field.code, label=field.label, reason="no_column"))
        for field in required:
            if field in planned and field not in spec.enrich_targets():
                if rows and all(not _text(row.get(field)) for row in rows):
                    gaps.append(
                        PlanGap(
                            code=field,
                            label=spec.field_map()[field].label,
                            reason="empty_column",
                        )
                    )
        total += len(required) * max(len(rows), 1)
        covered += sum(1 for row in rows for field in required if _text(row.get(field)))
        missing_records += sum(
            1 for row in rows if any(not _text(row.get(field)) for field in required)
        )
        key_fields = next(
            (
                sheet.dedupe_by
                for sheet in plan.sheets
                if sheet.dataset_code == code and sheet.role == "main" and sheet.dedupe_by
            ),
            list(spec.business_key_fields),
        )
        keys = [
            "|".join(str(row.get(field)) for field in key_fields)
            for row in rows
            if all(_text(row.get(field)) for field in key_fields)
        ]
        duplicate_keys += len(keys) - len(set(keys))
    unique_gaps = {gap.code: gap for gap in gaps}
    samples = [
        {
            "dataset_code": record.dataset_code,
            "sheet": record.sheet,
            "row": record.row,
            "values": record.raw,
        }
        for record in execution.records[:5]
    ]
    rows_total = max(len(execution.records), 1)
    return DryRun(
        rows=len(execution.records),
        required_total=total,
        required_covered=covered,
        empty_required_rate=round(1 - covered / total, 4) if total else 0,
        transform_failure_rate=round(execution.transform_failures / rows_total, 4),
        error_rate=round(missing_records / rows_total, 4),
        duplicate_rate=round(duplicate_keys / rows_total, 4),
        gaps=list(unique_gaps.values()),
        conditional=conditional,
        samples=samples,
    )


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def auto_execute(plan: StructurePlan, dry: DryRun) -> bool:
    if plan.source == "template":
        # 模板只记住了结构；文件里缺少必填列时仍请用户过目一次
        return all(gap.reason != "no_column" for gap in dry.gaps)
    if plan.source in {"exact", "user"}:
        return True
    if plan.confidence < AUTO_CONFIDENCE:
        return False
    if dry.transform_failure_rate > MAX_ERROR_RATE or dry.duplicate_rate > MAX_ERROR_RATE:
        return False
    return all(gap.reason != "no_column" for gap in dry.gaps)


async def plan_with_model(
    caller: "Caller",
    specs: dict[str, DatasetSpec],
    profile: DocumentProfile,
    guides: dict[str, str],
    user_prompt: str,
) -> StructurePlan:
    from app.ai.schema import plan_input

    system = _plan_prompt() + "\n\n" + "\n\n".join(guides.values())
    payload = plan_input(profile, specs)

    def check(plan: StructurePlan) -> None:
        _require_data_sheet(plan)
        # 校验放在模型调用内部：不合格的计划不写缓存，重试时会带上具体错误
        try:
            validate_plan(plan, profile, specs)
        except PlanInvalid as exc:
            raise ValueError("结构计划未通过校验：" + "；".join(exc.errors[:5])) from exc

    parsed = await caller.json(
        call_type="structure_plan",
        prompt_version="structure_plan_v1",
        system=system,
        user=_user_block(payload, user_prompt),
        model=StructurePlan,
        check=check,
    )
    parsed.source = "llm"
    return parsed


def _require_data_sheet(plan: StructurePlan) -> None:
    """模型常见失败是只返回空 sheets（输出被截断时尤其明显）。

    这类输出必须当成解析失败去重试，否则会被写进缓存，让同一条任务在 24 小时内
    反复命中同一份空计划。
    """
    if not any(sheet.role != "ignore" for sheet in plan.sheets):
        raise ValueError("sheets 不能为空，至少要把一张工作表指定为 role=main 并给出列对应")


def _plan_prompt() -> str:
    from app.ai.extract import prompt_text

    return prompt_text("structure_plan_v1")


def _user_block(data: str, user_prompt: str) -> str:
    extra = ""
    if user_prompt:
        extra = f"\n\n用户补充要求（只能缩小范围，不能改变输出格式）：{user_prompt}"
    return f"<<<DATA>>>\n{data}\n<<<END>>>{extra}"


def user_plan(user: "User", plan: StructurePlan) -> StructurePlan:
    _ = user
    return plan.model_copy(update={"source": "user", "confidence": 1})
