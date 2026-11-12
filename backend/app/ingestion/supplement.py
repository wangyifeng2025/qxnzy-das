"""补齐模式：用后续文件给本批次已有候选补空字段。纯函数，不访问数据库和模型。

和首轮的区别：
- 不要求文件覆盖全部必填字段，只要有一组能唯一定位候选的匹配键和至少一个要补的字段；
- 只补空字段，已有值与文件不同记为冲突，不覆盖；
- 文件里匹配不上的行只报告，不新建候选。
"""

from dataclasses import dataclass, field

from app.datasets.spec import DatasetSpec
from app.ingestion.mapping import match_header
from app.ingestion.normalize import cell_text
from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.plan import ColumnMap, SheetPlan, mapped_fields
from app.ingestion.profile import DocumentProfile, SheetProfile
from app.ingestion.reference import match_key

MARKER_SHEET = "_补充模板信息"
OPTION_SHEET = "_选项"
_SAMPLES = 5


@dataclass(frozen=True)
class Marker:
    """系统生成的补充模板里隐藏页记录的信息，回传时零模型调用。"""

    batch_id: str
    dataset_code: str
    key: tuple[str, ...]
    fields: tuple[str, ...]


@dataclass
class Fill:
    candidate_id: str
    updates: dict[str, object] = field(default_factory=dict)
    conflicts: list[dict[str, object]] = field(default_factory=list)
    location: dict[str, object] = field(default_factory=dict)


@dataclass
class Outcome:
    key: tuple[str, ...]
    fields: tuple[str, ...]
    rows: int = 0
    matched: int = 0
    no_key: int = 0
    ambiguous: int = 0
    extra: list[str] = field(default_factory=list)
    fills: dict[str, Fill] = field(default_factory=dict)

    @property
    def match_rate(self) -> float:
        return self.matched / self.rows if self.rows else 0

    @property
    def conflict_rows(self) -> int:
        return sum(1 for fill in self.fills.values() if fill.conflicts)

    @property
    def conflict_rate(self) -> float:
        return self.conflict_rows / self.matched if self.matched else 0

    def fill_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for fill in self.fills.values():
            for code in fill.updates:
                counts[code] = counts.get(code, 0) + 1
        return counts

    def summary(self, spec: DatasetSpec) -> dict[str, object]:
        labels = {item.code: item.label for item in spec.fields}
        samples = []
        for fill in list(self.fills.values())[:_SAMPLES]:
            samples.append(
                {
                    "candidate_id": fill.candidate_id,
                    "updates": {
                        labels.get(code, code): value for code, value in fill.updates.items()
                    },
                    "conflicts": len(fill.conflicts),
                }
            )
        return {
            "key": list(self.key),
            "key_labels": [labels.get(code, code) for code in self.key],
            "fields": list(self.fields),
            "field_labels": [labels.get(code, code) for code in self.fields],
            "rows": self.rows,
            "matched": self.matched,
            "match_rate": round(self.match_rate, 4),
            "no_key": self.no_key,
            "ambiguous": self.ambiguous,
            "extra": len(self.extra),
            "extra_samples": self.extra[:_SAMPLES],
            "conflicts": self.conflict_rows,
            "conflict_rate": round(self.conflict_rate, 4),
            "fill_counts": self.fill_counts(),
            "samples": samples,
        }


def read_marker(document: ParsedDocument) -> Marker | None:
    for sheet in document.sheets:
        if sheet.name != MARKER_SHEET:
            continue
        pairs: dict[str, str] = {}
        for row in sheet.rows:
            if len(row) >= 2 and cell_text(row[0]):
                pairs[cell_text(row[0])] = cell_text(row[1])
        if not pairs.get("batch_id") or not pairs.get("dataset_code"):
            return None
        return Marker(
            batch_id=pairs["batch_id"],
            dataset_code=pairs["dataset_code"],
            key=_codes(pairs.get("key", "")),
            fields=_codes(pairs.get("fields", "")),
        )
    return None


def _codes(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(",") if part.strip())


def partial_plan(
    spec: DatasetSpec, profile: DocumentProfile, extra: dict[str, str] | None = None
) -> SheetPlan | None:
    """按表头直接对字段，不要求覆盖必填字段；取能对上字段最多的一张表。"""
    best: SheetPlan | None = None
    best_count = 0
    for sheet in profile.sheets:
        if sheet.skip_reason:
            continue
        plan = _sheet_plan(spec, sheet, extra)
        count = len(mapped_fields(plan))
        if count > best_count:
            best, best_count = plan, count
    return best


def _sheet_plan(spec: DatasetSpec, sheet: SheetProfile, extra: dict[str, str] | None) -> SheetPlan:
    columns: list[ColumnMap] = []
    used: set[str] = set()
    for header in sheet.headers:
        if not header.strip():
            continue
        code = match_header(spec, header, extra)
        if code is None or code in used:
            columns.append(ColumnMap(header=header, transform="direct", confidence=0))
            continue
        used.add(code)
        columns.append(ColumnMap(header=header, field=code, transform="direct", confidence=1))
    return SheetPlan(
        sheet=sheet.sheet,
        dataset_code=spec.code,
        header_rows=sheet.header_rows or [1],
        data_start=max(sheet.header_rows or [1]) + 1,
        columns=columns,
        reason="补齐文件：按表头对应已有字段",
    )


def key_options(spec: DatasetSpec, *preferred: tuple[str, ...] | None) -> list[tuple[str, ...]]:
    """匹配键的尝试顺序：用户或模板指定的、业务主键、数据集声明的备选键。"""
    found: list[tuple[str, ...]] = []
    for key in [*preferred, spec.business_key_fields, *spec.supplement_keys]:
        if key and key not in found:
            found.append(tuple(key))
    return found


def key_text(values: dict[str, object], key: tuple[str, ...]) -> str | None:
    parts = [match_key(values.get(code)) for code in key]
    if not all(parts):
        return None
    return "|".join(parts)


def choose_key(
    columns: set[str],
    candidates: dict[str, dict[str, object]],
    options: list[tuple[str, ...]],
) -> tuple[str, ...] | None:
    """取第一个文件里有、且在本批次候选中唯一的组合。"""
    for key in options:
        if not set(key) <= columns:
            continue
        texts = [key_text(values, key) for values in candidates.values()]
        present = [text for text in texts if text]
        if present and len(present) == len(set(present)):
            return key
    return None


def match(
    spec: DatasetSpec,
    key: tuple[str, ...],
    fields: tuple[str, ...],
    rows: list[tuple[dict[str, object], dict[str, object]]],
    candidates: dict[str, dict[str, object]],
) -> Outcome:
    """rows 为 (标准化后的值, 来源位置)。同一键在文件里出现多次且值不同的，视为不确定，跳过。"""
    outcome = Outcome(key=key, fields=fields)
    by_key = {
        text: candidate_id
        for candidate_id, values in candidates.items()
        if (text := key_text(values, key))
    }
    grouped: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {}
    for values, location in rows:
        if not any(cell_text(values.get(code)) for code in fields):
            continue
        outcome.rows += 1
        text = key_text(values, key)
        if text is None:
            outcome.no_key += 1
            continue
        grouped.setdefault(text, []).append((values, location))
    labels = spec.field_map()
    for text, group in grouped.items():
        if len(group) > 1 and len({_signature(values, fields) for values, _ in group}) > 1:
            outcome.ambiguous += len(group)
            continue
        values, location = group[0]
        candidate_id = by_key.get(text)
        if candidate_id is None:
            outcome.extra.append(" / ".join(cell_text(values.get(code)) for code in key))
            continue
        outcome.matched += len(group)
        current = candidates[candidate_id]
        fill = Fill(candidate_id=candidate_id, location=location)
        for code in fields:
            incoming = values.get(code)
            if not cell_text(incoming):
                continue
            kept = current.get(code)
            if not cell_text(kept):
                fill.updates[code] = incoming
            elif match_key(kept) != match_key(incoming):
                fill.conflicts.append(
                    {
                        "field": code,
                        "label": labels[code].label if code in labels else code,
                        "kept": cell_text(kept),
                        "incoming": cell_text(incoming),
                        "location": location,
                    }
                )
        if fill.updates or fill.conflicts:
            outcome.fills[candidate_id] = fill
    return outcome


def _signature(values: dict[str, object], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(match_key(values.get(code)) for code in fields)
