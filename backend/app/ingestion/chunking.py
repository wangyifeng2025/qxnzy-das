from app.core.config import settings
from app.ingestion.parsers.base import ParsedBlock


def chunk_blocks(blocks: list[ParsedBlock]) -> list[tuple[dict[str, object], str]]:
    limit = settings.ai_max_chunk_chars
    chunks: list[tuple[dict[str, object], str]] = []
    current: list[str] = []
    location: dict[str, object] = {}
    size = 0
    for block in blocks:
        if size and size + len(block.text) > limit:
            chunks.append((location, "\n".join(current)))
            current = []
            size = 0
        if not current:
            location = dict(block.location)
        current.append(block.text)
        size += len(block.text)
    if current:
        chunks.append((location, "\n".join(current)))
    return chunks
