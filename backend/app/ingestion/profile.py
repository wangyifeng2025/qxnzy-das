"""文件画像：把原始网格变成可展示、可判断结构的描述。

画像只描述事实（表头候选、样本、合并区域、公式占比、是否有隐藏表/字典表），
不做字段匹配，也不调用模型。规划器和界面都以画像为输入。
"""

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.ingestion.parsers.base import ParsedDocument, ParsedSheet

HEADER_SCAN_ROWS = 30
_SAMPLE_ROWS = 5
_MERGED = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$")
_FOOTER = ("合计", "小计", "制表", "审核", "填表", "说明：", "备注：")
_HIDDEN_HINTS = ("说明", "注意事项", "填报须知", "填写须知")
_DICT_HINTS = ("字典", "数据字典", "下拉选项", "选项表", "dictionary")
_LEGEND_HINTS = ("代码表", "代码字典", "枚举")


class SheetProfile(BaseModel):
    sheet: str
    visible: bool
    rows: int
    cols: int
    merged: list[str] = Field(default_factory=list)
    header_rows: list[int] = Field(default_factory=list)
    header_texts: list[list[str]] = Field(default_factory=list)
    headers: list[str] = Field(default_factory=list)
    samples: list[list[str]] = Field(default_factory=list)
    empty_row_ratio: float = 0
    continuation_ratio: float = 0
    formula_ratio: float = 0
    number_formats: dict[str, str] = Field(default_factory=dict)
    duplicate_headers: list[str] = Field(default_factory=list)
    dict_ranges: list[str] = Field(default_factory=list)
    looks_like_columnar: bool = False
    looks_like_dict: bool = False
    skip_reason: str | None = None
    signature: str = ""


class DocumentProfile(BaseModel):
    kind: str
    sheets: list[SheetProfile] = Field(default_factory=list)

    @property
    def signatures(self) -> list[str]:
        return [sheet.signature for sheet in self.sheets if not sheet.skip_reason]

    def get(self, name: str) -> SheetProfile | None:
        return next((sheet for sheet in self.sheets if sheet.sheet == name), None)


def column_index(letter: str) -> int:
    value = 0
    for char in letter:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def fill_merged(rows: list[list[object]], merged: list[str]) -> list[list[object]]:
    """合并区域整块填上左上角的值；只影响读取，不改变原始解析结果。"""
    if not merged:
        return [list(row) for row in rows]
    grid = [list(row) for row in rows]
    for item in merged:
        matched = _MERGED.match(item.replace("$", ""))
        if matched is None:
            continue
        left = column_index(matched.group(1))
        top = int(matched.group(2)) - 1
        right = column_index(matched.group(3))
        bottom = int(matched.group(4)) - 1
        if top >= len(grid):
            continue
        value = grid[top][left] if left < len(grid[top]) else None
        for r in range(top, min(bottom, len(grid) - 1) + 1):
            for c in range(left, right + 1):
                if c < len(grid[r]):
                    grid[r][c] = value
    return grid


def text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("\u3000", " ").strip()


def clean_header(value: object) -> str:
    raw = re.sub(r"\s+", " ", text(value)).strip()
    return raw.removesuffix("*").strip()


def normalize_header(value: object) -> str:
    raw = clean_header(value)
    raw = re.sub(r"[（(][^）)]*[）)]$", "", raw).strip()
    return raw.replace(" ", "").lower()


def _filled(row: list[object]) -> list[str]:
    return [text(cell) for cell in row if text(cell)]


def _header_candidates(rows: list[list[object]]) -> list[int]:
    candidates: list[int] = []
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        values = _filled(row)
        if len(values) < 2 or len(set(values)) < 2:
            continue
        if values[0].startswith(_FOOTER):
            continue
        candidates.append(index)
    return candidates


def _star_ratio(row: list[object]) -> float:
    values = _filled(row)
    if not values:
        return 0
    return sum(1 for value in values if value.endswith(("*", "＊"))) / len(values)


def guess_header_rows(rows: list[list[object]]) -> list[int]:
    """返回 1 基的表头行号，例如专业导出表是 [2, 3]。"""
    candidates = _header_candidates(rows)
    if not candidates:
        return [1] if rows else []
    best = max(candidates, key=lambda index: (len(_filled(rows[index])), -index))
    following = best + 1
    if following < len(rows) and _star_ratio(rows[following]) >= 0.3:
        return [best + 1, following + 1]
    # 上一行是合并的父表头、本行是叶子表头时，两行都保留
    if best > 0 and len(_filled(rows[best - 1])) >= 2 and _star_ratio(rows[best]) >= 0.3:
        if _star_ratio(rows[best - 1]) < 0.3:
            return [best, best + 1]
    return [best + 1]


def compose_headers(rows: list[list[object]], header_rows: list[int]) -> list[str]:
    if not header_rows or not rows:
        return []
    width = max((len(row) for row in rows), default=0)
    headers: list[str] = []
    for column in range(width):
        chosen = ""
        for number in header_rows:
            index = number - 1
            if 0 <= index < len(rows) and column < len(rows[index]):
                value = text(rows[index][column])
                if value:
                    chosen = value
        headers.append(chosen)
    return headers


def guess_data_end(rows: list[list[object]], header_rows: list[int]) -> int:
    """返回 1 基的最后一行数据行号，去掉尾部空行和“合计/制表”脚注。"""
    start = (max(header_rows) if header_rows else 0) + 1
    end = len(rows)
    while end > start:
        values = _filled(rows[end - 1])
        if not values or values[0].startswith(_FOOTER):
            end -= 1
            continue
        break
    return end


def spreadsheet_signature(headers: list[str]) -> str:
    normalized = "|".join(normalize_header(item) for item in headers)
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def _empty_row_ratio(rows: list[list[object]], start: int) -> float:
    body = rows[start:]
    if not body:
        return 0
    return round(sum(1 for row in body if not _filled(row)) / len(body), 4)


def _continuation_ratio(rows: list[list[object]], start: int) -> float:
    body = [row for row in rows[start:] if _filled(row)]
    if not body:
        return 0
    continued = sum(
        1
        for row in body
        if not text(row[0]) and len(_filled(row)) >= 2 and len(_filled(row)) * 2 < len(row)
    )
    return round(continued / len(body), 4)


def _columnar(rows: list[list[object]], start: int) -> bool:
    body = [row for row in rows[start:] if _filled(row)]
    if len(body) < 4:
        return False
    width = max((len(row) for row in body), default=0)
    if width < 6 or width < len(body) * 2:
        return False
    first = [text(row[0]) for row in body]
    if any(not value for value in first):
        return False
    return sum(1 for value in first if re.search(r"[\u4e00-\u9fa5]", value)) >= len(first) * 0.8


def _dict_sheet(sheet: ParsedSheet) -> bool:
    name = sheet.name.lower()
    named = any(hint in name for hint in (*_DICT_HINTS, *_LEGEND_HINTS))
    few_columns = max((len(row) for row in sheet.rows), default=0) <= 3
    return (named and few_columns) or (few_columns and bool(sheet.dict_ranges))


def profile_sheet(sheet: ParsedSheet) -> SheetProfile:
    grid = fill_merged(sheet.rows, sheet.merged)
    header_rows = guess_header_rows(grid)
    headers = compose_headers(grid, header_rows)
    data_start = max(header_rows) if header_rows else 1
    end = guess_data_end(grid, header_rows)
    samples = [
        [text(cell) for cell in row] for row in grid[data_start:end][:_SAMPLE_ROWS] if _filled(row)
    ]
    duplicates = sorted({item for item in headers if item and headers.count(item) > 1})
    formats = _with_headers(headers, sheet.number_formats)
    return SheetProfile(
        sheet=sheet.name,
        visible=sheet.visible,
        rows=len(grid),
        cols=max((len(row) for row in grid), default=0),
        merged=sheet.merged,
        header_rows=header_rows,
        header_texts=[[text(cell) for cell in grid[number - 1]] for number in header_rows],
        headers=headers,
        samples=samples,
        empty_row_ratio=_empty_row_ratio(grid, data_start),
        continuation_ratio=_continuation_ratio(grid, data_start),
        formula_ratio=sheet.formula_ratio,
        number_formats=formats,
        duplicate_headers=duplicates,
        dict_ranges=sheet.dict_ranges,
        looks_like_columnar=_columnar(grid, data_start),
        looks_like_dict=_dict_sheet(sheet),
        skip_reason=_skip_reason(sheet, grid, header_rows, end),
        signature=spreadsheet_signature(headers),
    )


def _with_headers(headers: list[str], formats: dict[str, str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for letter, code in formats.items():
        index = column_index(letter)
        if index < len(headers) and headers[index]:
            found[headers[index]] = code
    return found


def _skip_reason(
    sheet: ParsedSheet, grid: list[list[object]], header_rows: list[int], end: int
) -> str | None:
    if not sheet.visible:
        return "隐藏工作表"
    if not grid:
        return "空工作表"
    if _dict_sheet(sheet):
        return "数据字典表"
    if any(hint in sheet.name for hint in _HIDDEN_HINTS):
        return "说明页"
    data_start = (max(header_rows) if header_rows else 1) + 1
    if end < data_start:
        return "没有数据行"
    return None


def profile_document(document: ParsedDocument) -> DocumentProfile:
    return DocumentProfile(
        kind="spreadsheet" if document.sheets else "text",
        sheets=[profile_sheet(sheet) for sheet in document.sheets],
    )


def sheet_map(document: ParsedDocument) -> dict[str, ParsedSheet]:
    return {sheet.name: sheet for sheet in document.sheets}


def header_pattern(profile: SheetProfile) -> Literal["normal", "columnar"]:
    return "columnar" if profile.looks_like_columnar else "normal"
