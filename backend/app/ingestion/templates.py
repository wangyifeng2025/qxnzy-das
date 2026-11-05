"""结构计划模板和表头别名的记忆。

用户确认一次计划后，相同的表头结构下次直接复用：不再调用模型，也不用重新确认。
别名的学习只发生在用户手改列对应并确认之后，避免把模型的猜测沉淀成规则。
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.spec import DatasetSpec
from app.ingestion.mapping import match_header
from app.ingestion.plan import StructurePlan
from app.ingestion.profile import DocumentProfile, normalize_header
from app.models.common import uuid_hex
from app.models.ingestion import IngestHeaderAlias, IngestPlanTemplate
from app.models.system import User


def _now() -> datetime:
    return datetime.now(UTC)


async def find_template(
    session: AsyncSession, dataset_code: str, signature: str, department_id: int | None
) -> IngestPlanTemplate | None:
    scopes: list[tuple[str, int | None]] = []
    if department_id is not None:
        scopes.append(("department", department_id))
    scopes.append(("global", None))
    for scope, dept in scopes:
        found = await session.scalar(
            select(IngestPlanTemplate).where(
                IngestPlanTemplate.dataset_code == dataset_code,
                IngestPlanTemplate.signature == signature,
                IngestPlanTemplate.scope == scope,
                IngestPlanTemplate.department_id.is_(None)
                if dept is None
                else IngestPlanTemplate.department_id == dept,
            )
        )
        if found is not None:
            return found
    return None


async def use_template(session: AsyncSession, template: IngestPlanTemplate) -> StructurePlan:
    template.hits += 1
    template.last_used_at = _now()
    plan = StructurePlan.model_validate(template.plan)
    plan.source = "template"
    plan.confidence = 1
    return plan


async def save_template(
    session: AsyncSession,
    plan: StructurePlan,
    profile: DocumentProfile,
    user: User,
    department_id: int | None,
    *,
    global_scope: bool,
) -> None:
    for sheet in plan.sheets:
        if sheet.role != "main" or not sheet.dataset_code:
            continue
        known = profile.get(sheet.sheet)
        signature = known.signature if known is not None else ""
        if not signature:
            continue
        scope = "global" if global_scope else "department"
        dept = None if global_scope else department_id
        existing = await session.scalar(
            select(IngestPlanTemplate).where(
                IngestPlanTemplate.dataset_code == sheet.dataset_code,
                IngestPlanTemplate.signature == signature,
                IngestPlanTemplate.scope == scope,
                IngestPlanTemplate.department_id.is_(None)
                if dept is None
                else IngestPlanTemplate.department_id == dept,
            )
        )
        payload = plan.model_copy(update={"source": "template", "confidence": 1})
        now = _now()
        if existing is None:
            session.add(
                IngestPlanTemplate(
                    id=uuid_hex(),
                    dataset_code=sheet.dataset_code,
                    signature=signature,
                    plan=payload.model_dump(mode="json"),
                    scope=scope,
                    department_id=dept,
                    confirmed_by=user.id,
                    hits=0,
                    created_at=now,
                    last_used_at=now,
                )
            )
        else:
            existing.plan = payload.model_dump(mode="json")
            existing.confirmed_by = user.id
            existing.last_used_at = now


async def load_aliases(
    session: AsyncSession, dataset_codes: set[str], department_id: int | None
) -> dict[str, dict[str, str]]:
    if not dataset_codes:
        return {}
    rows = await session.scalars(
        select(IngestHeaderAlias).where(IngestHeaderAlias.dataset_code.in_(dataset_codes))
    )
    found: dict[str, dict[str, str]] = {}
    for row in rows.all():
        if row.scope == "department" and row.department_id != department_id:
            continue
        found.setdefault(row.dataset_code, {})[row.header_norm] = row.field_code
    return found


async def learn_aliases(
    session: AsyncSession,
    spec: DatasetSpec,
    plan: StructurePlan,
    user: User,
    department_id: int | None,
) -> None:
    """用户确认过的列对应里，仍无法自动匹配的表头记为新别名。"""
    for sheet in plan.sheets:
        if sheet.dataset_code != spec.code:
            continue
        for column in sheet.columns:
            if column.field is None or not column.header:
                continue
            normalized = normalize_header(column.header)
            if not normalized:
                continue
            if match_header(spec, column.header) == column.field:
                continue
            scope = "department" if department_id is not None else "global"
            existing = await session.scalar(
                select(IngestHeaderAlias).where(
                    IngestHeaderAlias.dataset_code == spec.code,
                    IngestHeaderAlias.header_norm == normalized,
                    IngestHeaderAlias.scope == scope,
                    IngestHeaderAlias.department_id.is_(None)
                    if department_id is None
                    else IngestHeaderAlias.department_id == department_id,
                )
            )
            if existing is not None:
                existing.field_code = column.field
                existing.hits += 1
                continue
            session.add(
                IngestHeaderAlias(
                    id=uuid_hex(),
                    dataset_code=spec.code,
                    header_norm=normalized,
                    header_raw=column.header[:120],
                    field_code=column.field,
                    scope=scope,
                    department_id=department_id,
                    confirmed_by=user.id,
                    hits=1,
                    created_at=_now(),
                )
            )
