"""补传参照表：按共同字段把参照表里的值回填到已有候选。

例如课程表只有专业名称、专业代码是错的，补传一份“专业名称—专业代码”对照表，
就能按专业名称批量改好专业代码。纯函数，不访问数据库和模型。
"""

import re
import unicodedata
from dataclasses import dataclass, field

from app.datasets.spec import DatasetSpec
from app.ingestion.mapping import match_header
from app.ingestion.normalize import cell_text
from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.profile import fill_merged, guess_data_end, profile_sheet

_SAMPLE_LIMIT = 20
# “护理(天恩班)”“宠物医疗技术（学徒制）”这类班级后缀，精确匹配不到时去掉再试
_BRACKET = re.compile(r"\([^)]*\)$")


@dataclass
class RefColumn:
    header: str
    field: str | None


@dataclass
class RefSheet:
    name: str
    columns: list[RefColumn]
    rows: list[dict[str, str]]

    @property
    def fields(self) -> list[str]:
        return [column.field for column in self.columns if column.field]


@dataclass
class RefOutcome:
    key: list[str]
    fill: list[str]
    updates: dict[str, dict[str, str]] = field(default_factory=dict)
    matched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    overwritten: int = 0
    unmatched_samples: list[str] = field(default_factory=list)


def match_key(value: object) -> str:
    """全角半角、空白和大小写差异不影响匹配。"""
    return "".join(unicodedata.normalize("NFKC", cell_text(value)).split()).lower()


def read_sheets(spec: DatasetSpec, document: ParsedDocument) -> list[RefSheet]:
    sheets: list[RefSheet] = []
    for sheet in document.sheets:
        profile = profile_sheet(sheet)
        if profile.skip_reason or not profile.header_rows:
            continue
        columns: list[RefColumn] = []
        taken: set[str] = set()
        for header in profile.headers:
            code = match_header(spec, header) if header else None
            # 同一字段出现多列时只认第一列，避免两列值互相覆盖
            if code in taken:
                code = None
            if code:
                taken.add(code)
            columns.append(RefColumn(header=header, field=code))
        if not taken:
            continue
        grid = fill_merged(sheet.rows, sheet.merged)
        start = max(profile.header_rows)
        end = guess_data_end(grid, profile.header_rows)
        rows: list[dict[str, str]] = []
        for row in grid[start:end]:
            item = {
                column.field: cell_text(row[index])
                for index, column in enumerate(columns)
                if column.field and index < len(row) and cell_text(row[index])
            }
            if item:
                rows.append(item)
        if rows:
            sheets.append(RefSheet(name=sheet.name, columns=columns, rows=rows))
    return sheets


def suggest_key(sheet: RefSheet, candidates: list[dict[str, object]]) -> list[str]:
    """挑命中候选最多的单个字段做匹配键；命中相同时优先参照表里取值不重复的字段。"""
    best: tuple[int, int, int] | None = None
    chosen: list[str] = []
    for order, code in enumerate(sheet.fields):
        values = [match_key(row.get(code)) for row in sheet.rows if row.get(code)]
        known = set(values)
        hits = sum(1 for item in candidates if match_key(item.get(code)) in known)
        if hits == 0:
            continue
        unique = int(len(known) == len(values))
        score = (hits, unique, -order)
        if best is None or score > best:
            best, chosen = score, [code]
    return chosen


def compare(
    sheet: RefSheet,
    candidates: dict[str, dict[str, object]],
    key: list[str],
    fill: list[str],
    *,
    overwrite: bool,
) -> RefOutcome:
    outcome = RefOutcome(key=key, fill=fill)
    if not key or not fill:
        return outcome
    index, conflicted = _index(sheet, key, fill)
    missed: list[str] = []
    for candidate_id, values in candidates.items():
        parts = tuple(match_key(values.get(code)) for code in key)
        if not all(parts):
            outcome.unmatched += 1
            continue
        if parts in conflicted:
            outcome.ambiguous += 1
            continue
        found = index.get(parts)
        if found is None:
            loose = tuple(_BRACKET.sub("", part) for part in parts)
            if loose != parts and all(loose) and loose not in conflicted:
                found = index.get(loose)
        if found is None:
            outcome.unmatched += 1
            label = " / ".join(cell_text(values.get(code)) for code in key)
            if label not in missed:
                missed.append(label)
            continue
        outcome.matched += 1
        changes: dict[str, str] = {}
        for code, value in found.items():
            current = cell_text(values.get(code))
            if current == value:
                continue
            if current and not overwrite:
                continue
            if current:
                outcome.overwritten += 1
            changes[code] = value
        if changes:
            outcome.updates[candidate_id] = changes
    outcome.unmatched_samples = missed[:_SAMPLE_LIMIT]
    return outcome


def _index(
    sheet: RefSheet, key: list[str], fill: list[str]
) -> tuple[dict[tuple[str, ...], dict[str, str]], set[tuple[str, ...]]]:
    """同一个键在参照表里对应不同取值时视为有歧义，不回填。"""
    index: dict[tuple[str, ...], dict[str, str]] = {}
    conflicted: set[tuple[str, ...]] = set()
    for row in sheet.rows:
        parts = tuple(match_key(row.get(code)) for code in key)
        if not all(parts):
            continue
        values = {code: row[code] for code in fill if row.get(code)}
        known = index.setdefault(parts, {})
        for code, value in values.items():
            if code in known and known[code] != value:
                conflicted.add(parts)
            known.setdefault(code, value)
    return index, conflicted
