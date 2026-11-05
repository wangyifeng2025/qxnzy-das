"""按字段元数据做通用校验，各数据集再用钩子补充条件规则。"""

import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status

from app.datasets.spec import FieldSpec

Hook = Callable[[dict[str, object], list[str]], None]
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def check_fields(
    fields: tuple[FieldSpec, ...],
    payload: dict[str, object],
    options: dict[str, set[str]],
    departments: set[str],
    hook: Hook | None = None,
) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    data: dict[str, object] = {}
    for field in fields:
        if field.visible_when and data.get(field.visible_when) != "1":
            data[field.code] = None
            continue
        data[field.code] = _value(field, payload.get(field.code), options, departments, errors)
    if hook is not None:
        hook(data, errors)
    if errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="；".join(errors))
    return data, []


def _value(
    field: FieldSpec,
    raw: object,
    options: dict[str, set[str]],
    departments: set[str],
    errors: list[str],
) -> object:
    if field.kind == "number":
        return _number(raw, field.label, errors, required=field.required)
    if field.kind == "decimal":
        return _decimal(raw, field.label, errors, required=field.required)
    text = "" if raw is None else str(raw).strip()
    if field.kind == "month":
        return _month(text, field.label, errors, required=field.required)
    if field.kind == "date":
        return _date(text, field.label, errors, required=field.required)
    if not text:
        if field.required:
            errors.append(f"{field.label}不能为空")
        return None
    if field.max_length is not None and len(text) > field.max_length:
        errors.append(f"{field.label}不能超过 {field.max_length} 个字符")
    if field.dict_code == "departments":
        if text not in departments:
            errors.append(f"{field.label}不在可填范围内")
        return text
    if field.dict_code:
        allowed = options.get(field.dict_code, set())
        if text not in allowed:
            errors.append(f"{field.label}不在取值范围内")
    return text


def _month(text: str, label: str, errors: list[str], *, required: bool) -> str | None:
    if not text:
        if required:
            errors.append(f"{label}不能为空")
        return None
    if _MONTH.fullmatch(text) is None:
        errors.append(f"{label}须为 YYYY-MM")
    return text


def _date(text: str, label: str, errors: list[str], *, required: bool) -> str | None:
    if not text:
        if required:
            errors.append(f"{label}不能为空")
        return None
    if _DATE.fullmatch(text) is None:
        errors.append(f"{label}须为 YYYY-MM-DD")
    return text


def _number(raw: object, label: str, errors: list[str], *, required: bool) -> int | None:
    if raw is None or raw == "":
        if required:
            errors.append(f"{label}不能为空")
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        errors.append(f"{label}须为整数")
        return None
    try:
        number = int(str(raw))
    except ValueError:
        errors.append(f"{label}须为整数")
        return None
    if str(raw).strip() not in {str(number), f"{number}.0"}:
        errors.append(f"{label}须为整数")
        return None
    return number


def _decimal(raw: object, label: str, errors: list[str], *, required: bool) -> Decimal | None:
    if raw is None or raw == "":
        if required:
            errors.append(f"{label}不能为空")
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        errors.append(f"{label}不是有效金额")
        return None
    if not value.is_finite():
        errors.append(f"{label}不是有效金额")
        return None
    if value < 0:
        errors.append(f"{label}不能为负")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -4:
        errors.append(f"{label}最多保留 4 位小数")
    return value
