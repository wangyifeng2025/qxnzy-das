"""把不规范的单元格拆成标准字段。失败时保留原值，由流水线改走文本抽取。"""

import re

_RANGE = re.compile(
    r"(\d{4}\s*[./年-]\s*\d{1,2}\s*月?)\s*[-~～至到]+\s*(\d{4}\s*[./年-]\s*\d{1,2}\s*月?)"
)
_NAME_ID = re.compile(r"^(.+?)\s*[(（]\s*([0-9A-Za-z]+)\s*[)）]$")


def split_date_range(text: str) -> tuple[str, str] | None:
    matched = _RANGE.search(text.replace(" ", ""))
    if matched is None:
        return None
    return matched.group(1), matched.group(2)


def split_name_id(text: str) -> tuple[str, str] | None:
    matched = _NAME_ID.match(text.strip())
    if matched is None:
        return None
    return matched.group(1).strip(), matched.group(2).strip()


def concat_date(parts: list[str]) -> str | None:
    numbers = [re.sub(r"\D", "", part) for part in parts]
    if len(numbers) >= 2 and len(numbers[0]) == 4 and numbers[1]:
        month = numbers[1].zfill(2)
        if len(numbers) >= 3 and numbers[2]:
            return f"{numbers[0]}-{month}-{numbers[2].zfill(2)}"
        return f"{numbers[0]}-{month}"
    return None
