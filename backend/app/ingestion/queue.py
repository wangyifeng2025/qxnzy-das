"""入队失败时任务保持 queued，由定时任务补入队。"""

import logging
from uuid import uuid4

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus

from app.core.config import settings

logger = logging.getLogger(__name__)
_WAITING = {JobStatus.deferred, JobStatus.queued, JobStatus.in_progress}


async def enqueue_ingest(task_id: str, redis_url: str | None = None) -> bool:
    try:
        redis = await create_pool(RedisSettings.from_dsn(redis_url or settings.redis_url))
    except Exception:
        logger.warning("ingest enqueue failed task=%s", task_id)
        return False
    try:
        status = await Job(task_id, redis).status()
        if status in _WAITING:
            return True
        job_id = task_id if status == JobStatus.not_found else f"{task_id}-{uuid4().hex[:8]}"
        job = await redis.enqueue_job("run_ingest_task", task_id, _job_id=job_id)
        return job is not None
    except Exception:
        logger.warning("ingest enqueue failed task=%s", task_id)
        return False
    finally:
        await redis.aclose()
