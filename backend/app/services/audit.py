from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import client_ip_var, request_id_var
from app.models.system import AuditLog, User


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    summary: str,
    resource_id: str | None = None,
    actor: User | None = None,
    actor_account: str | None = None,
) -> None:
    """写入审计记录。调用方负责提交事务。"""
    account = actor.account if actor is not None else actor_account
    session.add(
        AuditLog(
            request_id=request_id_var.get() or None,
            actor_id=actor.id if actor is not None else None,
            actor_account=account,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary[:300],
            ip=client_ip_var.get(),
        )
    )
