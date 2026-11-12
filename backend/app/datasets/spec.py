from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.records import BizRecord
from app.models.system import User

Validate = Callable[..., tuple[dict[str, object], list[str]]]
Publish = Callable[[AsyncSession, BizRecord, dict[str, object], User], Awaitable[str]]
Relate = Callable[[AsyncSession, dict[str, object]], Awaitable[None]]


@dataclass(frozen=True)
class FieldSpec:
    code: str
    label: str
    kind: str
    group: str
    required: bool = False
    max_length: int | None = None
    dict_code: str | None = None
    visible_when: str | None = None
    sensitive: bool = False
    default: str | None = None
    aliases: tuple[str, ...] = ()
    hint: str | None = None
    example: str | None = None


@dataclass(frozen=True)
class Lookup:
    """用本表已有值查库补全其它字段，例如专业代码 → 专业名称、学制。"""

    source: str
    by: tuple[str, ...]
    fill: tuple[tuple[str, str], ...]
    scope: str = "published"  # published / draft / all
    name: str = ""
    confidence: float = 0.95


@dataclass(frozen=True)
class Derive:
    """不查库的确定性推导，例如按发起人所属部门补全院系、按姓名补全账号。"""

    kind: str
    fill: tuple[str, ...]


@dataclass(frozen=True)
class DatasetSpec:
    code: str
    name: str
    category: str
    review_department: str
    business_key_fields: tuple[str, ...]
    owner_field: str | None
    department_field: str
    list_fields: tuple[str, ...]
    fields: tuple[FieldSpec, ...]
    groups: tuple[tuple[str, str | None], ...]
    validate: Validate
    publish: Publish
    schema_version: int = 1
    owner_name_field: str | None = None
    relate: Relate | None = None
    lookups: tuple[Lookup, ...] = ()
    derives: tuple[Derive, ...] = ()
    # 补齐文件没有完整业务主键时，依次尝试的备选匹配键
    supplement_keys: tuple[tuple[str, ...], ...] = ()

    def field_map(self) -> dict[str, FieldSpec]:
        return {field.code: field for field in self.fields}

    def required_codes(self) -> list[str]:
        """提交级必填字段（不含条件必填）。"""
        return [field.code for field in self.fields if field.required and not field.visible_when]

    def conditional_fields(self) -> list[FieldSpec]:
        return [field for field in self.fields if field.visible_when]

    def enrich_targets(self) -> set[str]:
        found: set[str] = set()
        for rule in self.lookups:
            found.update(target for target, _source in rule.fill)
        return found


def jsonable(data: dict[str, Any]) -> dict[str, object]:
    converted: dict[str, object] = {}
    for key, value in data.items():
        converted[key] = str(value) if isinstance(value, Decimal) else value
    return converted
