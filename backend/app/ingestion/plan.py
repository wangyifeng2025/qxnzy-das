"""结构计划：描述一个文件怎么读，不包含任何数据值。

计划由模板、精确匹配、模型或用户给出，程序按计划执行，保证可复现、可审计。
"""

from typing import Literal

from pydantic import BaseModel, Field

Transform = Literal[
    "direct",
    "split_date_range",
    "split_name_id",
    "concat_date",
    "repeat_group",
    "narrative",
]
RowMode = Literal["single", "grouped", "repeat"]
HeaderPattern = Literal["normal", "columnar"]
PlanSource = Literal["template", "exact", "llm", "user", "text"]


class ColumnMap(BaseModel):
    """一列到标准字段的对应关系。语义与旧的 MappingItem 相同。"""

    header: str | None = None
    headers: list[str] | None = None  # 多列合成一个字段
    field: str | None = None
    fields: list[str] | None = None  # 一列拆成多个字段
    transform: Transform = "direct"
    group: int | None = None
    confidence: float = 0


class SheetPlan(BaseModel):
    sheet: str
    role: Literal["main", "reference", "ignore"] = "main"
    dataset_code: str | None = None
    header_rows: list[int] = Field(default_factory=lambda: [1])
    data_start: int = 2
    data_end: int | None = None
    header_pattern: HeaderPattern = "normal"
    columns: list[ColumnMap] = Field(default_factory=list)
    row_mode: RowMode = "single"
    group_key: list[str] = Field(default_factory=list)
    multi_value_fields: list[str] = Field(default_factory=list)
    multi_value_separators: list[str] = Field(default_factory=lambda: ["，", ",", "、", ";", "；"])
    # 这些字段都相同的行合并成一条候选；为空时按数据集业务主键合并
    dedupe_by: list[str] = Field(default_factory=list)
    reason: str = ""


class JoinSpec(BaseModel):
    reference_sheet: str
    main_sheet: str
    on: list[str] = Field(default_factory=list)
    fill: list[str] = Field(default_factory=list)


class StructurePlan(BaseModel):
    sheets: list[SheetPlan] = Field(default_factory=list)
    merge_sheets: list[list[str]] = Field(default_factory=list)
    joins: list[JoinSpec] = Field(default_factory=list)
    source: PlanSource = "llm"
    confidence: float = 0


class PlanGap(BaseModel):
    code: str
    label: str
    reason: Literal["no_column", "empty_column"] = "no_column"


class DryRun(BaseModel):
    rows: int = 0
    required_total: int = 0
    required_covered: int = 0
    empty_required_rate: float = 0
    transform_failure_rate: float = 0
    error_rate: float = 0
    duplicate_rate: float = 0
    gaps: list[PlanGap] = Field(default_factory=list)
    conditional: list[PlanGap] = Field(default_factory=list)
    samples: list[dict[str, object]] = Field(default_factory=list)
    auto: bool = False


def mapped_fields(sheet: SheetPlan) -> set[str]:
    """该表计划覆盖到的标准字段（不含描述列）。"""
    covered: set[str] = set()
    for column in sheet.columns:
        if column.transform == "narrative":
            continue
        if column.field:
            covered.add(column.field)
        covered.update(column.fields or [])
    covered.update(sheet.group_key)
    return covered
