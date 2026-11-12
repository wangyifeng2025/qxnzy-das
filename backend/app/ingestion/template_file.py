"""生成补充模板：预填匹配键、只留要补的列，字典列带下拉。回传时凭隐藏页零模型调用。"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.datasets.spec import DatasetSpec
from app.ingestion.normalize import cell_text
from app.ingestion.supplement import MARKER_SHEET, OPTION_SHEET

DATA_SHEET = "补充数据"
_KEY_FILL = PatternFill("solid", fgColor="E5E7EB")
_FIELD_FILL = PatternFill("solid", fgColor="FEF3C7")


def build(
    spec: DatasetSpec,
    batch_id: str,
    key: tuple[str, ...],
    fields: list[str],
    rows: list[dict[str, object]],
    options: dict[str, list[tuple[str, str]]],
) -> bytes:
    """rows 为候选当前值；options 为字典代码到 (值, 名称) 的列表。"""
    labels = spec.field_map()
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = DATA_SHEET
    columns = [*key, *fields]
    for index, code in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=labels[code].label)
        cell.font = Font(bold=True)
        cell.fill = _KEY_FILL if code in key else _FIELD_FILL
        sheet.column_dimensions[get_column_letter(index)].width = max(
            12, len(labels[code].label) * 2 + 4
        )
    for row_index, values in enumerate(rows, start=2):
        for index, code in enumerate(key, start=1):
            cell = sheet.cell(row=row_index, column=index, value=cell_text(values.get(code)))
            cell.number_format = "@"
    sheet.freeze_panes = "A2"
    choices = book.create_sheet(OPTION_SHEET)
    choices.sheet_state = "hidden"
    last = max(len(rows) + 1, 2)
    option_column = 0
    for index, code in enumerate(fields, start=len(key) + 1):
        item = labels[code]
        names = [label for _value, label in options.get(item.dict_code or "", [])]
        letter = get_column_letter(index)
        if not names or item.dict_code in {"departments", "titles"}:
            if item.kind in {"text", "number", "decimal"}:
                for row_index in range(2, last + 1):
                    sheet.cell(row=row_index, column=index).number_format = "@"
            continue
        option_column += 1
        option_letter = get_column_letter(option_column)
        choices.cell(row=1, column=option_column, value=item.label)
        for offset, name in enumerate(names, start=2):
            choices.cell(row=offset, column=option_column, value=name)
        rule = DataValidation(
            type="list",
            formula1=f"'{OPTION_SHEET}'!${option_letter}$2:${option_letter}${len(names) + 1}",
            allow_blank=True,
        )
        rule.error = f"请从下拉列表中选择{item.label}"
        rule.showErrorMessage = True
        sheet.add_data_validation(rule)
        rule.add(f"{letter}2:{letter}{last}")
    marker = book.create_sheet(MARKER_SHEET)
    marker.sheet_state = "hidden"
    for row_index, (name, value) in enumerate(
        [
            ("batch_id", batch_id),
            ("dataset_code", spec.code),
            ("key", ",".join(key)),
            ("fields", ",".join(fields)),
        ],
        start=1,
    ):
        marker.cell(row=row_index, column=1, value=name)
        marker.cell(row=row_index, column=2, value=value)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
