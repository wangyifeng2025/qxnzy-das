"""按数据集注册表生成模板，并用程序解析电子表格。不调用大模型。"""

import csv
from datetime import date, datetime
from io import BytesIO, StringIO
from zipfile import BadZipFile

from fastapi import HTTPException, status
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.spec import DatasetSpec, FieldSpec
from app.models.system import User
from app.schemas.records import ImportRow
from app.schemas.staff import DictOption
from app.services.records import _checked, _ensure_key, _key

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000


def template_bytes(spec: DatasetSpec) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "数据"
    for column, field in enumerate(spec.fields, start=1):
        cell = sheet.cell(1, column, field.label + ("*" if field.required else ""))
        cell.font = Font(bold=True)
        cell.comment = Comment(field.code, "qxnzy")
        sheet.column_dimensions[cell.column_letter].width = max(len(field.label) + 4, 14)
    note = book.create_sheet("说明")
    note["A1"] = "从第 2 行填写。带 * 的列必填。下拉字段填写选项名称。"
    note["A2"] = "开课学期和授课学期形如 2025-2026-1学期。导入只生成草稿或提交审核，不会直接发布。"
    note["A3"] = "同一业务主键再次导入会被拒绝。"
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def parse_upload(
    spec: DatasetSpec, filename: str, content: bytes, options: dict[str, list[DictOption]]
) -> list[tuple[int, dict[str, object]]]:
    if len(content) > MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="文件不能超过 5MB")
    lookups = _lookups(spec, options)
    if filename.lower().endswith(".csv"):
        rows = _csv_rows(spec, content)
    else:
        rows = _excel_rows(spec, content)
    if len(rows) > MAX_ROWS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"一次最多导入 {MAX_ROWS} 行")
    return [(number, _map_row(spec, raw, lookups)) for number, raw in rows]


async def preview_rows(
    session: AsyncSession,
    user: User,
    spec: DatasetSpec,
    rows: list[tuple[int, dict[str, object]]],
) -> list[ImportRow]:
    seen: set[str] = set()
    result: list[ImportRow] = []
    for number, payload in rows:
        errors: list[str] = []
        checked = payload
        try:
            data, _warnings, _errors, _department, _owner = await _checked(
                session, user, spec, payload
            )
            key = _key(spec, data)
            if key in seen:
                errors.append("表格内业务主键重复")
            else:
                await _ensure_key(session, spec, key, None)
                seen.add(key)
            checked = data
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "这一行无法导入"
            errors.append(detail)
        result.append(ImportRow(row=number, ok=not errors, errors=errors, payload=checked))
    return result


def _lookups(spec: DatasetSpec, options: dict[str, list[DictOption]]) -> dict[str, dict[str, str]]:
    lookups: dict[str, dict[str, str]] = {}
    for field in spec.fields:
        if field.dict_code in {None, "departments", "titles"}:
            continue
        choices = options.get(field.dict_code or "", [])
        lookups[field.code] = {item.label: item.value for item in choices}
        lookups[field.code].update({item.value: item.value for item in choices})
    return lookups


def _header_code(spec: DatasetSpec, text: object, comment: str | None) -> str | None:
    if comment and comment.strip() in spec.field_map():
        return comment.strip()
    raw = "" if text is None else str(text).strip().removesuffix("*").strip()
    if raw in spec.field_map():
        return raw
    for field in spec.fields:
        if field.label == raw:
            return field.code
    return None


def _excel_rows(spec: DatasetSpec, content: bytes) -> list[tuple[int, dict[str, object]]]:
    try:
        book = load_workbook(BytesIO(content), data_only=True)
    except (InvalidFileException, BadZipFile, ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="无法读取表格") from exc
    sheet = book.active
    headers: dict[int, str] = {}
    for cell in sheet[1]:
        comment = cell.comment.text if cell.comment is not None else None
        code = _header_code(spec, cell.value, comment)
        if code is not None and isinstance(cell.column, int):
            headers[cell.column] = code
    if not headers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="表头无法识别，请使用系统模板")
    rows: list[tuple[int, dict[str, object]]] = []
    for index, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        raw: dict[str, object] = {}
        for column, code in headers.items():
            raw[code] = values[column - 1] if column - 1 < len(values) else None
        if any(value not in {None, ""} for value in raw.values()):
            rows.append((index, raw))
    return rows


def _csv_rows(spec: DatasetSpec, content: bytes) -> list[tuple[int, dict[str, object]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="CSV 须为 UTF-8") from exc
    reader = csv.reader(StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="表头无法识别，请使用系统模板"
        ) from exc
    columns: dict[int, str] = {}
    for index, name in enumerate(header):
        code = _header_code(spec, name, None)
        if code is not None:
            columns[index] = code
    if not columns:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="表头无法识别，请使用系统模板")
    rows: list[tuple[int, dict[str, object]]] = []
    for offset, values in enumerate(reader, start=2):
        raw: dict[str, object] = {
            code: values[index] if index < len(values) else None for index, code in columns.items()
        }
        if any(value not in {None, ""} for value in raw.values()):
            rows.append((offset, raw))
    return rows


def _map_row(
    spec: DatasetSpec, raw: dict[str, object], lookups: dict[str, dict[str, str]]
) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for field in spec.fields:
        mapped[field.code] = _cell(field, raw.get(field.code), lookups.get(field.code, {}))
    return mapped


def _cell(field: FieldSpec, value: object, lookup: dict[str, str]) -> object:
    if isinstance(value, datetime):
        text = value.date().isoformat() if field.kind == "date" else value.strftime("%Y-%m")
    elif isinstance(value, date):
        text = value.isoformat()
    elif isinstance(value, bool):
        text = ""
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float) and value.is_integer():
        text = str(int(value))
    elif value is None:
        text = ""
    else:
        text = str(value).strip()
    if not text:
        return None
    if field.dict_code not in {None, "departments", "titles"}:
        return lookup.get(text, text)
    return text
