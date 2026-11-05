"""M5.5：画像、计划校验、试跑、模板记忆与确定性执行。"""

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.datasets.registry import get_dataset
from app.datasets.spec import Lookup
from app.ingestion.enrich import LookupCache, _lookup
from app.ingestion.execute import build_records
from app.ingestion.grounding import ground
from app.ingestion.mapping import exact_plan
from app.ingestion.parsers.spreadsheet import estimate_xlsx_cells, parse_xlsx
from app.ingestion.pipeline import IngestFailure, _guard_document, _guard_raw_size, _rule_key
from app.ingestion.plan import ColumnMap, SheetPlan, StructurePlan
from app.ingestion.planning import PlanInvalid, auto_execute, dry_run, validate_plan
from app.ingestion.profile import profile_document, profile_sheet
from app.ingestion.templates import find_template, save_template, use_template
from app.models.system import User

MAJOR = "ODS_ZYSZSJ"
MAJOR_FILE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "AI解析测试数据"
    / "1.2.1开设专业表-导出结果.xlsx"
)


def _major_document():
    return parse_xlsx(MAJOR_FILE.read_bytes())


def test_profile_marks_hidden_and_dict_sheets() -> None:
    book = Workbook()
    data = book.active
    assert data is not None
    data.title = "专业"
    data.append(["专业名称*", "专业代码*"])
    data.append(["生态农业技术", "410104"])
    hidden = book.create_sheet("说明")
    hidden.append(["本表填写说明"])
    hidden.sheet_state = "hidden"
    dictionary = book.create_sheet("数据字典")
    dictionary.append(["代码", "名称"])
    dictionary.append(["1", "选项"])
    buffer = BytesIO()
    book.save(buffer)
    document = parse_xlsx(buffer.getvalue())
    profile = profile_document(document)
    reasons = {sheet.sheet: sheet.skip_reason for sheet in profile.sheets}
    assert reasons["说明"] == "隐藏工作表"
    assert reasons["数据字典"] == "数据字典表"
    assert profile.get("专业") is not None
    assert profile.get("专业").header_rows == [1]  # type: ignore[union-attr]


def test_columnar_table_is_transposed_by_plan() -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["姓名", "张三", "李四"])
    sheet.append(["学号", "001", "002"])
    sheet.append(["专业", "生态农业技术", "园艺技术"])
    buffer = BytesIO()
    book.save(buffer)
    document = parse_xlsx(buffer.getvalue())
    plan = SheetPlan(
        sheet=document.sheets[0].name,
        header_rows=[1],
        data_start=2,
        header_pattern="columnar",
        columns=[
            ColumnMap(header="姓名", field="XM"),
            ColumnMap(header="学号", field="XH"),
            ColumnMap(header="专业", field="ZYMC"),
        ],
    )
    execution = build_records(document, StructurePlan(sheets=[plan]))
    assert [item.raw for item in execution.records] == [
        {"XM": "张三", "XH": "001", "ZYMC": "生态农业技术"},
        {"XM": "李四", "XH": "002", "ZYMC": "园艺技术"},
    ]


def test_major_plan_dry_run_reports_full_coverage() -> None:
    document = _major_document()
    profile = profile_sheet(document.sheets[0])
    spec = get_dataset(MAJOR)
    plan = exact_plan(spec, profile)
    assert plan is not None
    assert plan.row_mode == "grouped"
    assert "ZYJYXLMC" in plan.multi_value_fields
    validated = validate_plan(
        StructurePlan(sheets=[plan]), profile_document(document), {MAJOR: spec}
    )
    dry = dry_run(document, validated, {MAJOR: spec})
    assert dry.rows == 47
    assert dry.required_covered == dry.required_total
    assert dry.samples[0]["dataset_code"] == MAJOR
    assert dry.gaps == []


def test_plan_rejects_unknown_sheet_and_field() -> None:
    document = _major_document()
    profile = profile_document(document)
    spec = get_dataset(MAJOR)
    plan = StructurePlan(
        sheets=[
            SheetPlan(
                sheet="不存在的表",
                header_rows=[1],
                data_start=2,
                columns=[ColumnMap(header="专业名称*", field="NOPE")],
            )
        ]
    )
    try:
        validate_plan(plan, profile, {MAJOR: spec})
    except PlanInvalid as exc:
        assert any("不存在" in item for item in exc.errors)
    else:  # pragma: no cover
        raise AssertionError("应当拒绝不存在的表")


def test_plan_keeps_first_of_repeated_mapping() -> None:
    document = _major_document()
    profile = profile_document(document)
    spec = get_dataset(MAJOR)
    sheet_plan = exact_plan(spec, profile_sheet(document.sheets[0]))
    assert sheet_plan is not None
    first = next(column for column in sheet_plan.columns if column.field)
    repeated = first.model_copy()
    plan = StructurePlan(
        sheets=[sheet_plan.model_copy(update={"columns": [*sheet_plan.columns, repeated]})]
    )
    checked = validate_plan(plan, profile, {MAJOR: spec})
    targets = [column.field for column in checked.sheets[0].columns if column.field]
    assert targets.count(first.field) == 1
    assert checked.sheets[0].columns[-1].field is None


def test_template_with_missing_columns_waits_for_review() -> None:
    document = _major_document()
    spec = get_dataset(MAJOR)
    sheet_plan = exact_plan(spec, profile_sheet(document.sheets[0]))
    assert sheet_plan is not None
    full = StructurePlan(sheets=[sheet_plan], source="template", confidence=1)
    assert auto_execute(full, dry_run(document, full, {MAJOR: spec}))
    dropped = sheet_plan.model_copy(
        update={
            "columns": [
                column.model_copy(update={"field": None}) if column.field == "ZYMC" else column
                for column in sheet_plan.columns
            ]
        }
    )
    partial = StructurePlan(sheets=[dropped], source="template", confidence=1)
    dry = dry_run(document, partial, {MAJOR: spec})
    assert any(gap.code == "ZYMC" and gap.reason == "no_column" for gap in dry.gaps)
    assert not auto_execute(partial, dry)


def test_plan_dedupe_by_keeps_known_fields_and_counts_duplicates() -> None:
    document = _major_document()
    profile = profile_document(document)
    spec = get_dataset(MAJOR)
    sheet_plan = exact_plan(spec, profile_sheet(document.sheets[0]))
    assert sheet_plan is not None
    plan = StructurePlan(
        sheets=[sheet_plan.model_copy(update={"dedupe_by": ["ZYSSYXBMC", "NOPE"]})]
    )
    checked = validate_plan(plan, profile, {MAJOR: spec})
    assert checked.sheets[0].dedupe_by == ["ZYSSYXBMC"]
    dry = dry_run(document, checked, {MAJOR: spec})
    # 按院系判重时，同院系的多个专业都算重复
    assert dry.duplicate_rate > 0


async def test_lookup_queries_by_field_code() -> None:
    asked: list[dict[str, str]] = []

    class FakeCache(LookupCache):
        async def row(self, session, source, keys, scope):  # type: ignore[no-untyped-def]
            asked.append(keys)
            return {"ZYMC": "汽车检测与维修技术"}

    data: dict[str, object] = {"ZYDM": "460702"}
    sources: dict[str, dict[str, object]] = {}
    warnings: list[str] = []
    rule = Lookup(source="major", by=("ZYDM",), fill=(("ZYMC", "ZYMC"),), name="专业")
    await _lookup(None, data, sources, warnings, rule, FakeCache())  # type: ignore[arg-type]
    assert asked == [{"ZYDM": "460702"}]
    assert data["ZYMC"] == "汽车检测与维修技术"
    assert warnings == []


def test_rule_key_requires_every_field() -> None:
    expected = "rule:10721|汽车检测"
    assert _rule_key(["KCH", "ZYMC"], {"KCH": " 10721", "ZYMC": "汽车检测"}) == expected
    assert _rule_key(["KCH", "ZYMC"], {"KCH": "１０７２１", "ZYMC": "汽车 检测"}) == (
        "rule:10721|汽车检测"
    )
    assert _rule_key(["KCH", "ZYMC"], {"KCH": "10721"}) is None
    assert _rule_key([], {"KCH": "10721"}) is None


async def test_template_roundtrip_skips_planning(db_session: AsyncSession) -> None:
    document = _major_document()
    profile = profile_document(document)
    spec = get_dataset(MAJOR)
    sheet_plan = exact_plan(spec, profile_sheet(document.sheets[0]))
    assert sheet_plan is not None
    plan = StructurePlan(sheets=[sheet_plan])
    user = await db_session.scalar(select(User).where(User.account == "2015200012"))
    assert user is not None
    await save_template(
        db_session,
        plan,
        profile,
        user,
        user.department_id,
        global_scope=False,
    )
    await db_session.flush()
    signature = profile_sheet(document.sheets[0]).signature
    found = await find_template(db_session, MAJOR, signature, user.department_id)
    assert found is not None
    reused = await use_template(db_session, found)
    assert reused.source == "template"
    assert reused.sheets[0].sheet == sheet_plan.sheet
    assert reused.sheets[0].dataset_code == MAJOR


def test_grounding_drops_values_missing_from_source() -> None:
    source = "罗胜申报教学成果奖，日期2024-03"
    kept, warnings = ground(
        {"HJMC": "教学成果奖", "HJRQ": "2024-03", "HJR": "张三"},
        "罗胜申报教学成果奖，日期2024-03",
        source,
    )
    assert kept == {"HJMC": "教学成果奖", "HJRQ": "2024-03"}
    assert warnings
    dropped, _ = ground({"HJMC": "教学成果奖"}, "无关段落", source)
    assert dropped == {}


def test_cell_guard_counts_only_filled_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    """45 列 × 100 行的表只有少量非空单元格，不应因为空白补齐被判超限。"""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["姓名"])
    for index in range(99):
        sheet.append([f"值{index}"])
    # 表尾某个远处单元格有值，让网格宽度扩到 45 列，模拟导出文件里的零散数据。
    sheet.cell(row=50, column=45, value="尾巴")
    buffer = BytesIO()
    book.save(buffer)
    document = parse_xlsx(buffer.getvalue())
    assert document.cell_count == 100 * 45
    assert document.filled_cells == 101

    monkeypatch.setattr(settings, "ingest_max_cells", 1000)
    _guard_document("demo.xlsx", document)

    monkeypatch.setattr(settings, "ingest_max_cells", 50)
    with pytest.raises(IngestFailure) as caught:
        _guard_document("demo.xlsx", document)
    assert caught.value.code == "too_large"
    assert "101" in caught.value.message
    assert "50" in caught.value.message


def test_xlsx_estimate_blocks_before_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["姓名", "学号", "专业"])
    sheet.append(["张三", "001", "生态农业技术"])
    buffer = BytesIO()
    book.save(buffer)
    content = buffer.getvalue()

    estimate = estimate_xlsx_cells(content)
    assert estimate is not None and estimate >= 6

    monkeypatch.setattr(settings, "ingest_max_cells", 1)
    with pytest.raises(IngestFailure) as caught:
        _guard_raw_size(content)
    assert caught.value.code == "too_large"


def test_xlsx_estimate_returns_none_for_other_formats() -> None:
    assert estimate_xlsx_cells(b"not a zip") is None
