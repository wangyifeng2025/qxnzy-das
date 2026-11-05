from app.datasets.registry import get_dataset
from app.ingestion.parsers.base import ParsedDocument, ParsedSheet
from app.ingestion.reference import compare, read_sheets, suggest_key


def _majors() -> ParsedDocument:
    rows: list[list[object]] = [
        ["专业名称", "专业代码", "学制"],
        ["护理", "520201", "三年"],
        ["药学", "520301", "三年"],
        ["汽车检测与维修技术", "460702", "三年"],
        ["汽车检测与维修技术", "460799", "三年"],
    ]
    return ParsedDocument(sheets=[ParsedSheet(name="专业", rows=rows)])


def test_read_and_suggest_key_by_major_name() -> None:
    spec = get_dataset("ODS_KCJBSJ")
    [sheet] = read_sheets(spec, _majors())
    assert sheet.fields == ["ZYMC", "ZYDM", "XZM"]
    candidates = [{"ZYMC": "护理", "ZYDM": "10721"}, {"ZYMC": "药学", "ZYDM": "10721"}]
    assert suggest_key(sheet, candidates) == ["ZYMC"]


def test_compare_overwrites_matches_and_flags_ambiguous() -> None:
    spec = get_dataset("ODS_KCJBSJ")
    [sheet] = read_sheets(spec, _majors())
    candidates: dict[str, dict[str, object]] = {
        "a": {"ZYMC": "护理（天恩班）", "ZYDM": "10721"},
        "b": {"ZYMC": " 药学 ", "ZYDM": None},
        "c": {"ZYMC": "汽车检测与维修技术", "ZYDM": "10721"},
        "d": {"ZYMC": "软件工程", "ZYDM": None},
    }
    outcome = compare(sheet, candidates, ["ZYMC"], ["ZYDM", "XZM"], overwrite=True)
    assert outcome.updates["a"] == {"ZYDM": "520201", "XZM": "三年"}
    assert outcome.updates["b"] == {"ZYDM": "520301", "XZM": "三年"}
    assert outcome.ambiguous == 1
    assert outcome.unmatched_samples == ["软件工程"]
    assert outcome.overwritten == 1

    kept = compare(sheet, candidates, ["ZYMC"], ["ZYDM"], overwrite=False)
    assert "a" not in kept.updates
    assert kept.updates["b"] == {"ZYDM": "520301"}
