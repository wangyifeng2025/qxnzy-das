from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, require_permissions
from app.models.system import AuditLog, User
from app.schemas.common import Page
from app.schemas.system import AuditLogRead

router = APIRouter(prefix="/api/audit-logs", tags=["审计"])

ReadAudit = Annotated[User, Depends(require_permissions("audit:read"))]


@router.get("", response_model=Page[AuditLogRead], summary="审计日志")
async def list_audit_logs(
    session: DbSession,
    _: ReadAudit,
    keyword: Annotated[str | None, Query(description="账号 / 动作 / 摘要")] = None,
    action: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Page[AuditLogRead]:
    query = select(AuditLog)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                AuditLog.actor_account.ilike(like),
                AuditLog.action.ilike(like),
                AuditLog.summary.ilike(like),
            )
        )
    if action:
        query = query.where(AuditLog.action == action.strip())
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (
        await session.scalars(
            query.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return Page(
        items=[AuditLogRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
