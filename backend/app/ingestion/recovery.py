"""把卡住或尚未入队的任务重新放回队列。"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.pipeline import _fail, _now
from app.models.ingestion import IngestTask


async def tasks_to_enqueue(session: AsyncSession) -> list[str]:
    cutoff = _now() - timedelta(minutes=5)
    stuck = (
        await session.scalars(
            select(IngestTask).where(
                IngestTask.status.in_(["parsing", "extracting"]),
                IngestTask.heartbeat_at.is_not(None),
                IngestTask.heartbeat_at < cutoff,
            )
        )
    ).all()
    ready: list[str] = []
    for task in stuck:
        if task.attempts >= 3:
            _fail(task, "stuck", "任务长时间无响应")
            continue
        task.status = "queued"
        task.error_code = None
        task.error_message = None
        ready.append(task.id)
    waiting = (
        await session.scalars(select(IngestTask.id).where(IngestTask.status == "queued"))
    ).all()
    for task_id in waiting:
        if task_id not in ready:
            ready.append(task_id)
    return ready
