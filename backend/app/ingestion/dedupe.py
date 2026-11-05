"""业务主键查重：区分“同批次合并”“可补充已有草稿”“与在途/已发布记录冲突”。"""

import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.spec import DatasetSpec
from app.ingestion.normalize import cell_text
from app.models.records import BizRecord
from app.models.system import User

EDITABLE = {"draft", "returned"}


@dataclass(frozen=True)
class Existing:
    id: str
    status: str
    filler_account: str


@dataclass(frozen=True)
class DupResult:
    kind: str  # none / batch / editable / conflict
    record_id: str | None = None
    key: str | None = None


class KeyIndex:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], Existing] = {}

    async def load(self, session: AsyncSession, dataset_codes: set[str]) -> None:
        rows = await session.execute(
            select(
                BizRecord.id,
                BizRecord.dataset_code,
                BizRecord.business_key,
                BizRecord.status,
                BizRecord.filler_account,
            ).where(
                BizRecord.dataset_code.in_(dataset_codes),
                BizRecord.deleted_at.is_(None),
            )
        )
        for identifier, dataset, key, status, account in rows:
            self._rows[(dataset, key)] = Existing(identifier, status, account)

    def get(self, dataset: str, key: str) -> Existing | None:
        return self._rows.get((dataset, key))


def business_key(spec: DatasetSpec, values: dict[str, object]) -> str | None:
    if not all(cell_text(values.get(field)) for field in spec.business_key_fields):
        return None
    return "|".join(str(values[field]) for field in spec.business_key_fields)


def normalize_business_values(spec: DatasetSpec, values: dict[str, object]) -> str | None:
    """去掉空格、全角差异后的主键，用于发现“看起来一样”的重复。"""
    parts: list[str] = []
    for field in spec.business_key_fields:
        text = unicodedata.normalize("NFKC", cell_text(values.get(field))).lower()
        if not text:
            return None
        parts.append("".join(text.split()))
    return "|".join(parts)


def check(
    spec: DatasetSpec,
    values: dict[str, object],
    index: KeyIndex,
    user: User,
    seen: dict[str, str] | None = None,
) -> DupResult:
    key = business_key(spec, values)
    if key is None:
        return DupResult("none")
    normalized = normalize_business_values(spec, values) or key
    if seen is not None and normalized in seen:
        return DupResult("batch", seen[normalized], key)
    existing = index.get(spec.code, key)
    if existing is not None:
        if existing.status in EDITABLE and existing.filler_account == user.account:
            return DupResult("editable", existing.id, key)
        return DupResult("conflict", existing.id, key)
    return DupResult("none", None, key)


def remember(seen: dict[str, str], spec: DatasetSpec, values: dict[str, object], ref: str) -> None:
    normalized = normalize_business_values(spec, values)
    if normalized is not None:
        seen[normalized] = ref
