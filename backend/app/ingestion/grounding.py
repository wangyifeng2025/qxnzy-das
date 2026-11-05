"""证据核验：模型给出的字段值必须在原文中能逐字找到。"""

import re
import unicodedata

_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text)
    return _SPACE.sub("", folded).lower()


def evidence_in_source(evidence: str, source: str) -> bool:
    target = normalize(evidence)
    if not target:
        return False
    return target in normalize(source)


def value_in_evidence(value: object, evidence: str) -> bool:
    text = str(value).strip()
    if not text:
        return True
    if normalize(text) in normalize(evidence):
        return True
    digits = re.sub(r"\D", "", text)
    return bool(digits) and digits in re.sub(r"\D", "", evidence)


def ground(
    values: dict[str, object], evidence: str, source: str
) -> tuple[dict[str, object], list[str]]:
    """只保留有原文依据的字段；证据整体对不上时整条记录不采纳。"""
    if not evidence or not evidence_in_source(evidence, source):
        return {}, ["证据不足"]
    kept: dict[str, object] = {}
    dropped: list[str] = []
    for key, value in values.items():
        if value in {None, ""}:
            continue
        if value_in_evidence(value, evidence):
            kept[key] = value
        else:
            dropped.append(key)
    return kept, ([f"证据不足：{len(dropped)} 个字段已忽略"] if dropped else [])
