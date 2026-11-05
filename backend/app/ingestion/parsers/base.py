from dataclasses import dataclass, field


@dataclass
class ParsedSheet:
    """原始网格：不做表头假设，也不折叠续行。"""

    name: str
    rows: list[list[object]]
    row_numbers: list[int] = field(default_factory=list)
    visible: bool = True
    merged: list[str] = field(default_factory=list)
    dict_ranges: list[str] = field(default_factory=list)
    formula_ratio: float = 0.0
    number_formats: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedBlock:
    location: dict[str, object]
    text: str


@dataclass
class ParsedDocument:
    sheets: list[ParsedSheet] = field(default_factory=list)
    blocks: list[ParsedBlock] = field(default_factory=list)
    page_count: int = 0
    cell_count: int = 0

    @property
    def text_chars(self) -> int:
        return sum(len(block.text) for block in self.blocks)

    @property
    def filled_cells(self) -> int:
        """非空单元格数量。

        `cell_count` 是网格面积，会被补齐的空白列和表尾空行放大；判断文件是否过大
        要看真正有数据的单元格，否则一份 45 列、2000 行的普通课程表也会被判超限。
        """
        return sum(
            1
            for sheet in self.sheets
            for row in sheet.rows
            for cell in row
            if cell is not None and cell != ""
        )

    @property
    def row_count(self) -> int:
        return sum(len(sheet.rows) for sheet in self.sheets)
