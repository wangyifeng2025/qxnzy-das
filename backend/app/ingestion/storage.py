"""把上传文件存到按年月和任务划分的目录，文件名使用随机标识。"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.models.common import uuid_hex


def file_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_upload(task_id: str, original_name: str, content: bytes) -> str:
    suffix = Path(original_name).suffix.lower()
    now = datetime.now(UTC)
    directory = settings.upload_dir / f"{now:%Y}" / f"{now:%m}" / task_id
    directory.mkdir(parents=True, exist_ok=True)
    relative = directory / f"{uuid_hex()}{suffix}"
    relative.write_bytes(content)
    return str(relative)


def read_upload(stored_path: str) -> bytes:
    path = Path(stored_path)
    if not path.is_file():
        raise FileNotFoundError(stored_path)
    return path.read_bytes()


def delete_upload(stored_path: str) -> None:
    path = Path(stored_path)
    if path.is_file():
        path.unlink()
