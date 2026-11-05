import logging

from app.ai.client import HttpxLLMClient
from app.db import async_session_factory
from app.ingestion.pipeline import run_pipeline
from app.ingestion.queue import enqueue_ingest
from app.ingestion.recovery import tasks_to_enqueue

logger = logging.getLogger(__name__)


async def run_ingest_task(_ctx: dict[str, object], task_id: str) -> None:
    async with async_session_factory() as session:
        await run_pipeline(session, task_id, HttpxLLMClient())
        await session.commit()
    logger.info("ingest worker finished task=%s", task_id)


async def recover_ingest_tasks(_ctx: dict[str, object]) -> None:
    async with async_session_factory() as session:
        task_ids = await tasks_to_enqueue(session)
        await session.commit()
    for task_id in task_ids:
        await enqueue_ingest(task_id)
