"""确定性执行器：按结构计划把文件读成原值记录。

模型不参与这里。所有续行合并、横表转置、多表拼接、跨表关联都在程序里完成，
因此同样的文件和计划必然得到同样的结果。
"""

from dataclasses import dataclass, field

from app.ingestion.mapping import convert_columns, empty_record
from app.ingestion.normalize import cell_text
from app.ingestion.parsers.base import ParsedDocument, ParsedSheet
from app.ingestion.plan import JoinSpec, SheetPlan, StructurePlan
from app.ingestion.profile import fill_merged, text

_SOURCE_LIMIT = 2000


@dataclass
class Record:
    dataset_code: str
    sheet: str
    row: int
    raw: dict[str, object]
    source_text: str
    sheet_plan: SheetPlan


@dataclass
class Execution:
    records: list[Record] = field(default_factory=list)
    transform_failures: int = 0
    rows: int = 0


def build_records(
    document: ParsedDocument, plan: StructurePlan, *, limit: int | None = None
) -> Execution:
    sheets = {sheet.name: sheet for sheet in document.sheets}
    merged_members = {name for group in plan.merge_sheets for name in group[1:]}
    execution = Execution()
    for sheet_plan in plan.sheets:
        if sheet_plan.role != "main" or sheet_plan.sheet in merged_members:
            continue
        members = _group_members(plan, sheet_plan.sheet)
        for member in members:
            sheet = sheets.get(member)
            if sheet is None:
                continue
            execution.transform_failures += _run_sheet(
                sheet, sheet_plan, execution.records, limit=limit
            )
    execution.rows = len(execution.records)
    if plan.joins:
        _apply_joins(plan, document, execution.records)
    return execution


def _group_members(plan: StructurePlan, name: str) -> list[str]:
    for group in plan.merge_sheets:
        if group and group[0] == name:
            return list(group)
    return [name]


def _run_sheet(
    sheet: ParsedSheet, plan: SheetPlan, records: list[Record], *, limit: int | None
) -> int:
    grid = fill_merged(sheet.rows, sheet.merged)
    if plan.header_pattern == "columnar":
        grid = _transpose(grid)
        headers = [text(cell) for cell in grid[0]] if grid else []
        rows = [(number, grid[number - 1]) for number in range(2, len(grid) + 1)]
    else:
        headers = _headers(grid, plan)
        rows = _slice(grid, plan)
    failures = 0
    emitted = 0
    current: dict[str, object] | None = None
    current_row: tuple[int, str] | None = None
    for number, row in rows:
        if limit is not None and emitted >= limit:
            break
        converted, fallback = convert_columns(headers, row, plan.columns)
        source = _source_text(headers, row)
        if fallback is not None:
            failures += 1
            records.append(
                Record(
                    dataset_code=plan.dataset_code or "",
                    sheet=sheet.name,
                    row=number,
                    raw={},
                    source_text=fallback,
                    sheet_plan=plan,
                )
            )
            emitted += 1
            continue
        for raw in converted:
            if empty_record(raw):
                continue
            if plan.row_mode == "grouped":
                if current is not None and _continued(raw, plan):
                    _merge_values(current, raw, plan)
                    continue
                if current is not None and current_row is not None:
                    _append(records, plan, sheet.name, current_row, current)
                    emitted += 1
                if limit is not None and emitted >= limit:
                    current = None
                    break
                current = dict(raw)
                current_row = (number, source)
                continue
            _append(records, plan, sheet.name, (number, source), raw)
            emitted += 1
    if current is not None and current_row is not None:
        _append(records, plan, sheet.name, current_row, current)
    return failures


def _append(
    records: list[Record],
    plan: SheetPlan,
    sheet: str,
    where: tuple[int, str],
    raw: dict[str, object],
) -> None:
    records.append(
        Record(
            dataset_code=plan.dataset_code or "",
            sheet=sheet,
            row=where[0],
            raw=raw,
            source_text=where[1],
            sheet_plan=plan,
        )
    )


def _headers(grid: list[list[object]], plan: SheetPlan) -> list[str]:
    width = max((len(row) for row in grid), default=0)
    headers: list[str] = []
    for column in range(width):
        chosen = ""
        for number in plan.header_rows:
            index = number - 1
            if 0 <= index < len(grid) and column < len(grid[index]):
                value = text(grid[index][column])
                if value:
                    chosen = value
        headers.append(chosen)
    return headers


def _slice(grid: list[list[object]], plan: SheetPlan) -> list[tuple[int, list[object]]]:
    start = max(plan.data_start, 1)
    end = plan.data_end if plan.data_end is not None else len(grid)
    return [
        (number, grid[number - 1])
        for number in range(start, min(end, len(grid)) + 1)
        if number - 1 < len(grid)
    ]


def _transpose(grid: list[list[object]]) -> list[list[object]]:
    width = max((len(row) for row in grid), default=0)
    return [
        [grid[row][column] if column < len(grid[row]) else None for row in range(len(grid))]
        for column in range(width)
    ]


def _continued(raw: dict[str, object], plan: SheetPlan) -> bool:
    if not plan.group_key:
        return False
    if any(cell_text(raw.get(field)) for field in plan.group_key):
        return False
    others = [
        code for code in raw if code not in plan.group_key and code not in plan.multi_value_fields
    ]
    if any(cell_text(raw.get(code)) for code in others):
        return False
    return any(cell_text(raw.get(field)) for field in plan.multi_value_fields)


def _merge_values(target: dict[str, object], raw: dict[str, object], plan: SheetPlan) -> None:
    separators = plan.multi_value_separators or ["，"]
    for code in plan.multi_value_fields:
        value = cell_text(raw.get(code))
        if not value:
            continue
        existing = cell_text(target.get(code))
        items = _split(existing, separators)
        for part in _split(value, separators):
            if part and part not in items:
                items.append(part)
        target[code] = "，".join(items)


def _split(value: str, separators: list[str]) -> list[str]:
    items = [value] if value else []
    for separator in separators:
        items = [part for item in items for part in item.split(separator)]
    return [item.strip() for item in items if item.strip()]


def _source_text(headers: list[str], row: list[object]) -> str:
    parts = []
    for index, header in enumerate(headers):
        value = cell_text(row[index]) if index < len(row) else ""
        if value and header:
            parts.append(f"{header}：{value}")
    return "；".join(parts)[:_SOURCE_LIMIT]


def _apply_joins(plan: StructurePlan, document: ParsedDocument, records: list[Record]) -> None:
    sheets = {sheet.name: sheet for sheet in document.sheets}
    by_sheet = {item.sheet: item for item in plan.sheets}
    for join in plan.joins:
        reference_plan = by_sheet.get(join.reference_sheet)
        main_plan = by_sheet.get(join.main_sheet)
        if reference_plan is None or main_plan is None:
            continue
        lookup = _reference_index(sheets.get(join.reference_sheet), reference_plan, join)
        for record in records:
            if record.sheet != join.main_sheet:
                continue
            key = tuple(cell_text(record.raw.get(field)) for field in join.on)
            if not all(key):
                continue
            found = lookup.get(key)
            if found is None:
                continue
            for code in join.fill:
                if not cell_text(record.raw.get(code)) and cell_text(found.get(code)):
                    record.raw[code] = found[code]


def _reference_index(
    sheet: ParsedSheet | None, plan: SheetPlan, join: JoinSpec
) -> dict[tuple[str, ...], dict[str, object]]:
    if sheet is None:
        return {}
    grid = fill_merged(sheet.rows, sheet.merged)
    headers = _headers(grid, plan)
    index: dict[tuple[str, ...], dict[str, object]] = {}
    for _number, row in _slice(grid, plan):
        converted, _fallback = convert_columns(headers, row, plan.columns)
        for raw in converted:
            key = tuple(cell_text(raw.get(field)) for field in join.on)
            if all(key) and key not in index:
                index[key] = raw
    return index
