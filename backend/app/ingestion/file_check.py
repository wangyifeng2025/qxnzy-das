"""扩展名、声明类型和文件头必须一致。"""

import zipfile
from io import BytesIO

from fastapi import HTTPException, status

from app.core.config import settings

ALLOWED = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_LOOSE_MIME = {"application/octet-stream", "binary/octet-stream", ""}


class FileRejected(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


def check_upload(filename: str, declared_mime: str | None, content: bytes) -> tuple[str, str]:
    suffix = _suffix(filename)
    if suffix not in ALLOWED:
        raise FileRejected("只接受 xlsx、xls、csv、pdf、docx")
    limit = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > limit:
        raise FileRejected(f"文件不能超过 {settings.max_upload_size_mb}MB")
    mime = (declared_mime or "").split(";", 1)[0].strip().lower()
    if mime not in _LOOSE_MIME and mime != ALLOWED[suffix] and not _mime_alias(suffix, mime):
        raise FileRejected("文件类型与扩展名不一致")
    detected = _detect(content)
    if detected != suffix:
        raise FileRejected("文件内容与扩展名不一致")
    return suffix, ALLOWED[suffix]


def _suffix(filename: str) -> str:
    dot = filename.rfind(".")
    if dot < 0 or "/" in filename or "\\" in filename:
        return ""
    return filename[dot:].lower()


def _mime_alias(suffix: str, mime: str) -> bool:
    aliases = {
        ".csv": {"text/plain", "application/csv", "application/vnd.ms-excel"},
        ".xls": {"application/octet-stream"},
    }
    return mime in aliases.get(suffix, set())


def _detect(content: bytes) -> str:
    if content.startswith(b"%PDF"):
        return ".pdf"
    if content.startswith(b"\xd0\xcf\x11\xe0"):
        return ".xls"
    if content.startswith(b"PK"):
        return _zip_kind(content)
    if _looks_textual(content):
        return ".csv"
    return ""


def _zip_kind(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return ""
    if any(name.startswith("word/") for name in names):
        return ".docx"
    if any(name.startswith("xl/") for name in names):
        return ".xlsx"
    return ""


def _looks_textual(content: bytes) -> bool:
    sample = content[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def rejection(exc: FileRejected) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message)
