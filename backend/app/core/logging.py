"""统一日志配置：控制台 + 轮转文件，自动带上请求 ID。

API 和 worker 分别写各自的文件，避免多个进程同时轮转同一个文件。
日志文件默认放在 storage/logs/，该目录已被 .gitignore 忽略。
"""

import logging
import logging.config
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.request_context import request_id_var

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RequestIdFilter(logging.Filter):
    """把当前请求 ID 注入日志记录；worker 里没有请求时记为 -。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"  # type: ignore[attr-defined]
        return True


def _log_file(service: str) -> Path | None:
    if not settings.log_to_file:
        return None
    path = settings.log_dir / f"{service}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def build_config(service: str) -> dict[str, Any]:
    """构造 dictConfig 配置。service 只决定文件名，例如 api、worker。"""
    level = settings.log_level.upper()
    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "standard",
            "filters": ["request_id"],
            "stream": "ext://sys.stdout",
        }
    }
    names = ["console"]
    file_path = _log_file(service)
    if file_path is not None:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": level,
            "formatter": "standard",
            "filters": ["request_id"],
            "filename": str(file_path),
            "maxBytes": settings.log_max_bytes,
            "backupCount": settings.log_backup_count,
            "encoding": "utf-8",
        }
        names.append("file")
    plain: dict[str, Any] = {"handlers": names, "level": level, "propagate": False}
    return {
        "version": 1,
        # 关掉这个开关会把 uvicorn、arq 自己的 logger 一并禁用
        "disable_existing_loggers": False,
        "filters": {"request_id": {"()": "app.core.logging.RequestIdFilter"}},
        "formatters": {"standard": {"format": _FORMAT, "datefmt": _DATE_FORMAT}},
        "handlers": handlers,
        "loggers": {
            "app": plain,
            # uvicorn 启动时会给自己装 stderr handler，纳入文件需要覆盖它
            "uvicorn": plain,
            "uvicorn.error": plain,
            # 访问日志由 app.access 统一记录（能带上请求 ID），这里避免重复输出
            "uvicorn.access": {**plain, "level": "WARNING"},
            "arq": plain,
            "sqlalchemy.engine": {**plain, "level": "WARNING"},
        },
        "root": {"handlers": names, "level": level},
    }


def setup_logging(service: str) -> None:
    logging.config.dictConfig(build_config(service))
