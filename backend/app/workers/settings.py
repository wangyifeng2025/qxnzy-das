from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import setup_logging
from app.workers.ingest import recover_ingest_tasks, run_ingest_task

# arq 只配置自己的 logger，root 不设 handler 时 INFO 会全部丢失
setup_logging("worker")


class WorkerSettings:
    functions = [run_ingest_task]
    cron_jobs = [cron(recover_ingest_tasks, minute=set(range(60)))]  # type: ignore[arg-type]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    job_timeout = 30 * 60
    max_tries = 1

    @staticmethod
    async def on_startup(_ctx: dict[str, object]) -> None:
        # arq CLI 在导入本模块之后才配置自己的 logger，这里覆盖一次避免重复输出
        setup_logging("worker")
