"""表格文件解析：只如实读取原始网格，不猜表头、不折叠续行。

表头识别、续行分组、横表转置都由画像（profile.py）和结构计划（planning.py）决定，
解析阶段出错时后面无法纠正，因此这里不做任何结构判断。
"""

import csv
import re
import zipfile
from collections.abc import Sequence
from io import BytesIO, StringIO

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from app.ingestion.parsers.base import ParsedDocument, ParsedSheet

_FORMAT_SCAN_ROWS = 30
_DIMENSION = re.compile(rb'<dimension ref="([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?"')


def estimate_xlsx_cells(content: bytes) -> int | None:
    """不加载工作簿，先从工作表 XML 的 dimension 粗略估算网格面积。

    openpyxl 加载一份几十万单元格的表要几十秒并占满内存；先用这个估算做快速拦截，
    避免超大文件把 worker 拖死。估算值不会小于真实网格面积，因此不会误拒。
    """
    if not zipfile.is_zipfile(BytesIO(content)):
        return None
    total = 0
    found = False
    with zipfile.ZipFile(BytesIO(content)) as archive:
        for name in archive.namelist():
            if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
                continue
            with archive.open(name) as handle:
                head = handle.read(2048)
            match = _DIMENSION.search(head)
            if match is None:
                continue
            found = True
            start_col = _column_index(match.group(1))
            start_row = int(match.group(2))
            end_col = _column_index(match.group(3) or match.group(1))
            end_row = int(match.group(4) or match.group(2))
            total += max(0, end_col - start_col + 1) * max(0, end_row - start_row + 1)
    return total if found else None


def _column_index(letters: bytes) -> int:
    index = 0
    for char in letters.decode("ascii"):
        index = index * 26 + (ord(char) - 64)
    return index


def parse_xlsx(content: bytes) -> ParsedDocument:
    values = load_workbook(BytesIO(content), data_only=True)
    formulas = load_workbook(BytesIO(content), data_only=False)
    document = ParsedDocument()
    for sheet in values.worksheets:
        rows = _grid(sheet)
        merged = [str(item) for item in sheet.merged_cells.ranges]
        document.sheets.append(
            ParsedSheet(
                name=sheet.title,
                rows=rows,
                row_numbers=list(range(1, len(rows) + 1)),
                visible=sheet.sheet_state == "visible",
                merged=merged,
                dict_ranges=_dict_ranges(sheet),
                formula_ratio=_formula_ratio(formulas[sheet.title]),
                number_formats=_number_formats(sheet),
            )
        )
        document.cell_count += sum(len(row) for row in rows)
    return document


def parse_xls(content: bytes) -> ParsedDocument:
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    document = ParsedDocument()
    for sheet in book.sheets():
        rows: list[list[object]] = [
            [sheet.cell_value(row, column) for column in range(sheet.ncols)]
            for row in range(sheet.nrows)
        ]
        document.sheets.append(
            ParsedSheet(
                name=sheet.name,
                rows=rows,
                row_numbers=list(range(1, len(rows) + 1)),
                visible=sheet.visibility == 0,
            )
        )
        document.cell_count += sum(len(row) for row in rows)
    return document


def parse_csv(content: bytes) -> ParsedDocument:
    text = content.decode("utf-8-sig")
    rows: list[list[object]] = [list(row) for row in csv.reader(StringIO(text))]
    sheet = ParsedSheet(name="csv", rows=rows, row_numbers=list(range(1, len(rows) + 1)))
    return ParsedDocument(sheets=[sheet], cell_count=sum(len(row) for row in rows))


def _grid(sheet: object) -> list[list[object]]:
    raw = [list(row) for row in sheet.iter_rows(values_only=True)]  # type: ignore[attr-defined]
    width = max((len(row) for row in raw), default=0)
    for row in raw:
        row.extend([None] * (width - len(row)))
    return raw


def _dict_ranges(sheet: object) -> list[str]:
    validation = getattr(sheet, "data_validations", None)
    if validation is None:
        return []
    found: list[str] = []
    for item in getattr(validation, "dataValidation", []) or []:
        formula = getattr(item, "formula1", "") or ""
        if "!" in formula:
            found.append(str(formula).strip('"'))
    return found


def _formula_ratio(sheet: object) -> float:
    formulas = 0
    filled = 0
    for row in sheet.iter_rows():  # type: ignore[attr-defined]
        for cell in row:
            if getattr(cell, "data_type", None) == "f":
                formulas += 1
            elif cell.value not in {None, ""}:
                filled += 1
    total = formulas + filled
    return round(formulas / total, 4) if total else 0.0


def _number_formats(sheet: object) -> dict[str, str]:
    found: dict[str, str] = {}
    width = int(getattr(sheet, "max_column", 0) or 0)
    height = min(int(getattr(sheet, "max_row", 0) or 0), _FORMAT_SCAN_ROWS)
    for column in range(1, width + 1):
        letter = get_column_letter(column)
        for row in range(1, height + 1):
            cell = sheet.cell(row=row, column=column)  # type: ignore[attr-defined]
            code = getattr(cell, "number_format", "General")
            if cell.value not in {None, ""} and code != "General":
                found[letter] = str(code)
                break
    return found


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def text_of(values: Sequence[object]) -> list[str]:
    return [_text(value) for value in values]
