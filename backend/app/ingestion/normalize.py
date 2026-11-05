"""把原文值收成标准格式。匹配不到的字典值保留原文，交给校验标出错误。"""

import re

from app.datasets.spec import DatasetSpec, FieldSpec

_MONTH = re.compile(r"^(\d{4})[./年-](\d{1,2})月?$")
_DATE = re.compile(r"^(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})日?$")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).replace("\u3000", " ").strip()
    return text


def normalize_payload(
    spec: DatasetSpec,
    raw: dict[str, object],
    lookups: dict[str, dict[str, str]],
) -> dict[str, object]:
    data: dict[str, object] = {}
    for field in spec.fields:
        text = cell_text(raw.get(field.code))
        if not text:
            data[field.code] = field.default if field.default is not None else None
            continue
        data[field.code] = _one(field, text, lookups.get(field.dict_code or "", {}))
    return data


def _one(field: FieldSpec, text: str, lookup: dict[str, str]) -> object:
    if field.kind in {"number", "decimal"}:
        return text.replace(",", "").replace("，", "")
    if field.kind == "month":
        return _month(text) or text
    if field.kind == "date":
        return _date(text) or text
    if field.dict_code not in {None, "departments", "titles"}:
        return lookup.get(text, text)
    return text


def _month(text: str) -> str | None:
    compact = _COMPACT.fullmatch(text)
    if compact is not None:
        return f"{compact.group(1)}-{compact.group(2)}"
    matched = _MONTH.fullmatch(text)
    if matched is None:
        return None
    month = matched.group(2).zfill(2)
    if not 1 <= int(month) <= 12:
        return None
    return f"{matched.group(1)}-{month}"


def _date(text: str) -> str | None:
    matched = _DATE.fullmatch(text)
    if matched is None:
        return None
    month = matched.group(2).zfill(2)
    day = matched.group(3).zfill(2)
    return f"{matched.group(1)}-{month}-{day}"
