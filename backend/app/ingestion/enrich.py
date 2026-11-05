"""确定性补全：按规则查已发布数据或推导院系、人员。

模型看不到本地数据库，也不允许编造关联字段；这里的结果单独标记来源，
前端可以看到“专业名称来自已发布专业库”这样的依据。
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.access import filler_type_for
from app.datasets.spec import DatasetSpec, Lookup
from app.ingestion.normalize import cell_text
from app.models.academic import Course, Major
from app.models.records import BizRecord
from app.models.staff import StaffMember
from app.models.system import Department, User

_SOURCES = {
    "major": (Major, "ODS_ZYSZSJ", ("ZYDM", "ZYMC")),
    "course": (Course, "ODS_KCJBSJ", ("KCH", "ZYDM", "NJ")),
    "staff": (StaffMember, "ODS_JZGJBSJ", ("JGH", "JSXM")),
}


@dataclass
class EnrichResult:
    values: dict[str, object]
    warnings: list[str] = field(default_factory=list)
    sources: dict[str, dict[str, object]] = field(default_factory=dict)


class LookupCache:
    """同一任务内复用查询结果，避免 2700 行逐行查库。"""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, object] | None] = {}
        self._departments: dict[str, str] | None = None
        self._drafts: dict[str, list[dict[str, object]]] = {}

    async def row(
        self, session: AsyncSession, source: str, keys: dict[str, str], scope: str
    ) -> dict[str, object] | None:
        cache_key = (source, "|".join(f"{key}={value}" for key, value in sorted(keys.items())))
        if cache_key in self._rows:
            return self._rows[cache_key]
        found = await self._published(session, source, keys)
        if found is None and scope in {"draft", "all"}:
            found = await self._draft(session, source, keys)
        self._rows[cache_key] = found
        return found

    async def _published(
        self, session: AsyncSession, source: str, keys: dict[str, str]
    ) -> dict[str, object] | None:
        entry = _SOURCES.get(source)
        if entry is None:
            return None
        model, _dataset, allowed = entry
        clauses = [
            getattr(model, key) == value
            for key, value in keys.items()
            if key in allowed and hasattr(model, key)
        ]
        if len(clauses) != len(keys):
            return None
        row = await session.scalar(select(model).where(*clauses).limit(1))
        if row is None:
            return None
        return {column.key: getattr(row, column.key) for column in model.__table__.columns}

    async def _draft(
        self, session: AsyncSession, source: str, keys: dict[str, str]
    ) -> dict[str, object] | None:
        entry = _SOURCES.get(source)
        if entry is None:
            return None
        _model, dataset_code, _allowed = entry
        if dataset_code not in self._drafts:
            rows = await session.scalars(
                select(BizRecord).where(
                    BizRecord.dataset_code == dataset_code,
                    BizRecord.status.in_(("draft", "returned")),
                    BizRecord.deleted_at.is_(None),
                )
            )
            self._drafts[dataset_code] = [dict(row.payload or {}) for row in rows.all()]
        for payload in self._drafts[dataset_code]:
            if all(cell_text(payload.get(key)) == value for key, value in keys.items()):
                return payload
        return None

    async def department(self, session: AsyncSession, name: str) -> str | None:
        if self._departments is None:
            rows = await session.scalars(select(Department))
            self._departments = {}
            for item in rows.all():
                self._departments[item.name] = item.name
                if item.short_name:
                    self._departments[item.short_name] = item.name
        if name in self._departments:
            return self._departments[name]
        stripped = name.rstrip("部系")
        for known, canonical in self._departments.items():
            if known.rstrip("部系") == stripped:
                return canonical
        return None


async def enrich(
    session: AsyncSession,
    spec: DatasetSpec,
    user: User,
    data: dict[str, object],
    sources: dict[str, dict[str, object]],
    cache: LookupCache,
    *,
    task_department_id: int | None = None,
) -> EnrichResult:
    warnings: list[str] = []
    _department(spec, user, data, sources, task_department_id)
    await _normalize_department(session, spec, data, sources, cache)
    await _owner(session, spec, data, sources, warnings, task_department_id)
    for rule in spec.lookups:
        await _lookup(session, data, sources, warnings, rule, cache)
    return EnrichResult(values=data, warnings=list(dict.fromkeys(warnings)), sources=sources)


def _department(
    spec: DatasetSpec,
    user: User,
    data: dict[str, object],
    sources: dict[str, dict[str, object]],
    task_department_id: int | None,
) -> None:
    field_code = spec.department_field
    if not field_code or data.get(field_code) or user.department is None:
        return
    kind = filler_type_for(user, spec)
    if kind in {"teacher", "department"} or task_department_id is not None:
        data[field_code] = user.department.name
        sources[field_code] = {"source": "derive", "ref": "department", "score": 0.95}


async def _normalize_department(
    session: AsyncSession,
    spec: DatasetSpec,
    data: dict[str, object],
    sources: dict[str, dict[str, object]],
    cache: LookupCache,
) -> None:
    field_code = spec.department_field
    value = cell_text(data.get(field_code))
    if not field_code or not value:
        return
    canonical = await cache.department(session, value)
    if canonical is not None and canonical != value:
        data[field_code] = canonical
        sources[field_code] = {"source": "lookup", "ref": "department", "score": 0.95}


async def _owner(
    session: AsyncSession,
    spec: DatasetSpec,
    data: dict[str, object],
    sources: dict[str, dict[str, object]],
    warnings: list[str],
    task_department_id: int | None,
) -> None:
    if spec.owner_field is None or spec.owner_name_field is None:
        return
    if data.get(spec.owner_field):
        return
    name = cell_text(data.get(spec.owner_name_field))
    if not name:
        return
    matches = list(await session.scalars(select(User).where(User.name == name)))
    if task_department_id is not None:
        scoped = [item for item in matches if item.department_id == task_department_id]
        if scoped:
            matches = scoped
    if len(matches) == 1:
        data[spec.owner_field] = matches[0].account
        sources[spec.owner_field] = {"source": "derive", "ref": "user", "score": 0.95}
    elif len(matches) > 1:
        warnings.append("需选择人员")


async def _lookup(
    session: AsyncSession,
    data: dict[str, object],
    sources: dict[str, dict[str, object]],
    warnings: list[str],
    rule: Lookup,
    cache: LookupCache,
) -> None:
    targets = [target for target, _source in rule.fill]
    if all(cell_text(data.get(target)) for target in targets):
        return
    keys: dict[str, str] = {}
    for code in rule.by:
        value = cell_text(data.get(code))
        if not value:
            return
        keys[code] = value
    found = await cache.row(session, rule.source, keys, rule.scope)
    if found is None:
        warnings.append(f"未匹配到{rule.name or '关联数据'}")
        return
    for target, source in rule.fill:
        if cell_text(data.get(target)):
            continue
        value = found.get(source)
        if value in {None, ""}:
            continue
        data[target] = str(value)
        sources[target] = {
            "source": "lookup",
            "ref": rule.source,
            "score": rule.confidence,
        }
