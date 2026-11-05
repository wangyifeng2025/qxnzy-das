"""表头匹配与单行/分组展开。纯函数，不访问模型和数据库。"""

import re

from app.datasets.spec import DatasetSpec
from app.ingestion.normalize import cell_text
from app.ingestion.plan import ColumnMap, SheetPlan, mapped_fields
from app.ingestion.profile import SheetProfile, clean_header, normalize_header
from app.ingestion.transforms import concat_date, split_date_range, split_name_id

_NOTE = re.compile(r"[（(][^）)]*[）)]$")


def match_header(spec: DatasetSpec, header: str, extra: dict[str, str] | None = None) -> str | None:
    raw = _NOTE.sub("", header.strip().removesuffix("*").strip()).strip()
    if not raw:
        return None
    if raw in spec.field_map():
        return raw
    target = normalize_header(raw)
    known = spec.field_map()
    if extra and target in extra and extra[target] in known:
        return extra[target]
    for field in spec.fields:
        if normalize_header(field.label) == target:
            return field.code
    for field in spec.fields:
        for alias in field.aliases:
            if normalize_header(alias) == target:
                return field.code
    if len(raw) < 2:
        return None
    suffixed = [
        field.code
        for field in spec.fields
        if normalize_header(field.label).endswith(target)
        or any(normalize_header(alias).endswith(target) for alias in field.aliases)
    ]
    return suffixed[0] if len(suffixed) == 1 else None


def exact_plan(
    spec: DatasetSpec, profile: SheetProfile, extra: dict[str, str] | None = None
) -> SheetPlan | None:
    """表头能完整对上必填字段时，直接生成计划，零模型调用。"""
    columns: list[ColumnMap] = []
    used: set[str] = set()
    matched = 0
    for header in profile.headers:
        if not header.strip():
            continue
        code = match_header(spec, header, extra)
        if code is None:
            columns.append(ColumnMap(header=header, transform="direct", confidence=0))
            continue
        if code in used:
            return None
        used.add(code)
        matched += 1
        columns.append(ColumnMap(header=header, field=code, transform="direct", confidence=1))
    if matched == 0 or not set(spec.required_codes()) <= used:
        return None
    row_mode: str = "single"
    group_key: list[str] = []
    multi: list[str] = []
    reason = "表头与标准字段完全对应"
    if profile.continuation_ratio >= 0.05 and set(spec.business_key_fields) <= used:
        row_mode = "grouped"
        group_key = list(spec.business_key_fields)
        multi = sorted(
            mapped_fields(SheetPlan(sheet=profile.sheet, columns=columns, group_key=group_key))
            - set(group_key)
        )
        reason = "表头完全对应，且检测到续行，按业务主键合并"
    return SheetPlan(
        sheet=profile.sheet,
        dataset_code=spec.code,
        header_rows=profile.header_rows or [1],
        data_start=max(profile.header_rows or [1]) + 1,
        header_pattern="normal",
        columns=columns,
        row_mode=row_mode,  # type: ignore[arg-type]
        group_key=group_key,
        multi_value_fields=multi,
        reason=reason,
    )


def convert_columns(
    headers: list[str],
    row: list[object],
    columns: list[ColumnMap],
) -> tuple[list[dict[str, object]], str | None]:
    """按列计划把一行展开成一条或多条原值记录。"""
    pools: dict[str, list[int]] = {}
    for index, header in enumerate(headers):
        for key in {clean_header(header), normalize_header(header)}:
            pools.setdefault(key, []).append(index)

    def take(header: str) -> str:
        for key in (clean_header(header), normalize_header(header)):
            found = pools.get(key)
            if found:
                index = found.pop(0)
                return cell_text(row[index]) if index < len(row) else ""
        return ""

    if any(column.transform == "narrative" for column in columns):
        narrative = _row_text(headers, row)
        if narrative:
            return [], narrative
    base: dict[str, object] = {}
    groups: dict[int, dict[str, object]] = {}
    for column in columns:
        if column.transform == "narrative":
            continue
        if column.transform == "concat_date" and column.field and column.headers:
            merged = concat_date([take(header) for header in column.headers])
            if merged is None:
                return [], _row_text(headers, row)
            base[column.field] = merged
            continue
        text = ""
        if column.headers:
            text = "".join(take(header) for header in column.headers)
        elif column.header is not None:
            text = take(column.header)
        target = base
        if column.transform == "repeat_group" and column.group:
            target = groups.setdefault(column.group, {})
        if column.transform == "split_date_range" and column.fields and len(column.fields) >= 2:
            parts = split_date_range(text) if text else None
            if text and parts is None:
                return [], _row_text(headers, row)
            if parts is not None:
                target[column.fields[0]] = parts[0]
                target[column.fields[1]] = parts[1]
            continue
        if column.transform == "split_name_id" and column.fields and len(column.fields) >= 2:
            parts = split_name_id(text) if text else None
            if text and parts is None:
                return [], _row_text(headers, row)
            if parts is not None:
                target[column.fields[0]] = parts[0]
                target[column.fields[1]] = parts[1]
            continue
        if column.field:
            target[column.field] = text
    if not groups:
        return [base], None
    records = [
        {**base, **values}
        for values in groups.values()
        if any(cell_text(value) for value in values.values())
    ]
    return records or [base], None


def _row_text(headers: list[str], row: list[object]) -> str:
    pairs = []
    for index, header in enumerate(headers):
        value = cell_text(row[index]) if index < len(row) else ""
        if value and header:
            pairs.append(f"{header}：{value}")
    return "；".join(pairs)


def empty_record(record: dict[str, object]) -> bool:
    return not any(cell_text(value) for value in record.values())
