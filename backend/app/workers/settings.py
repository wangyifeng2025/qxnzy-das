from arq.connections import RedisSettings

from app.core.config import settings


class WorkerSettings:
    functions: list[object] = []
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
