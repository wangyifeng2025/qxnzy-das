"""来源评分、完成度与分诊。纯函数，便于回归测试。"""

from app.datasets.spec import DatasetSpec
from app.ingestion.normalize import cell_text

# 来源可信度：手工/批量最高，文件与模板次之，模型抽取最低。
SCORES = {
    "manual": 1.0,
    "bulk": 1.0,
    "derive": 0.95,
    "lookup": 0.95,
    "file": 0.95,
    "file_weak": 0.85,
    "join": 0.9,
    "ai": 0.8,
    "completion": 0.7,
}

AUTO_THRESHOLD = 0.9
TRIAGE_AUTO = "auto"
TRIAGE_REVIEW = "review"
TRIAGE_MISSING = "missing"
TRIAGE_DUPLICATE = "duplicate"

TRIAGE_LABELS = {
    TRIAGE_AUTO: "可直接确认",
    TRIAGE_REVIEW: "需要确认",
    TRIAGE_MISSING: "待补材料",
    TRIAGE_DUPLICATE: "重复",
}


def score_of(source: dict[str, object] | None) -> float:
    if not source:
        return 0
    kind = str(source.get("source") or "")
    if kind == "file" and source.get("weak"):
        kind = "file_weak"
    return float(source.get("score") or SCORES.get(kind, 0))


def should_auto(values: dict[str, object], errors: list[str], sources: dict[str, dict]) -> bool:
    if errors:
        return False
    for field, value in values.items():
        if cell_text(value) and score_of(sources.get(field)) < AUTO_THRESHOLD:
            return False
    return True


def visible_fields(spec: DatasetSpec, values: dict[str, object]) -> list[str]:
    codes: list[str] = []
    for field in spec.fields:
        if field.visible_when and values.get(field.visible_when) != "1":
            continue
        codes.append(field.code)
    return codes


def completeness(spec: DatasetSpec, values: dict[str, object]) -> int:
    required = [
        field.code
        for field in spec.fields
        if field.required and field.code in visible_fields(spec, values)
    ]
    if not required:
        return 100
    filled = sum(1 for code in required if cell_text(values.get(code)))
    return round(filled * 100 / len(required))


def missing_required(spec: DatasetSpec, values: dict[str, object]) -> list[str]:
    return [
        field.code
        for field in spec.fields
        if field.required
        and field.code in visible_fields(spec, values)
        and not cell_text(values.get(field.code))
    ]


def business_key_ready(spec: DatasetSpec, values: dict[str, object]) -> bool:
    return all(cell_text(values.get(field)) for field in spec.business_key_fields)


def classify(
    spec: DatasetSpec,
    values: dict[str, object],
    errors: list[str],
    sources: dict[str, dict],
    *,
    duplicate: str | None,
    conflict: bool,
) -> str:
    if duplicate:
        return TRIAGE_DUPLICATE
    if conflict:
        return TRIAGE_REVIEW
    missing = missing_required(spec, values)
    if missing:
        return TRIAGE_MISSING
    if errors or not should_auto(values, errors, sources):
        return TRIAGE_REVIEW
    return TRIAGE_AUTO
