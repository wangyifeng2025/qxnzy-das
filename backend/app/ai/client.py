"""OpenAI 兼容的对话接口。业务代码只依赖 LLMClient。"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import resolved_ai, settings

logger = logging.getLogger(__name__)
_BACKOFF = (2, 8, 30)
_semaphore: asyncio.Semaphore | None = None


class ModelUnavailable(Exception):
    """网络、超时或服务端错误，调用方应把任务标为可重试失败。"""


class ModelRejected(Exception):
    """请求本身不被接受，例如密钥错误。"""


@dataclass
class LLMResult:
    content: str
    tokens_in: int
    tokens_out: int


class LLMClient(Protocol):
    async def complete(self, *, system: str, user: str) -> LLMResult: ...


def _limit() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.ai_max_concurrency)
    return _semaphore


class HttpxLLMClient:
    async def complete(self, *, system: str, user: str) -> LLMResult:
        _provider, base, key, model = resolved_ai()
        if not key:
            raise ModelUnavailable("模型服务暂不可用")
        payload: dict[str, object] = {
            "model": model,
            "temperature": 0,
            "max_tokens": settings.ai_max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if settings.ai_disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        async with _limit():
            return await _post(base, key, payload, with_json_mode=True)


async def _post(
    base: str, key: str, payload: dict[str, object], *, with_json_mode: bool
) -> LLMResult:
    body = dict(payload)
    if with_json_mode:
        body["response_format"] = {"type": "json_object"}
    last_error: Exception | None = None
    for attempt, delay in enumerate((0, *_BACKOFF)):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                response = await client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=body,
                )
        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning("模型请求失败 type=%s attempt=%s", type(exc).__name__, attempt)
            continue
        if response.status_code == 400 and with_json_mode:
            return await _post(base, key, payload, with_json_mode=False)
        if response.status_code == 429 or response.status_code >= 500:
            last_error = ModelUnavailable("模型服务暂不可用")
            logger.warning("模型请求失败 status=%s attempt=%s", response.status_code, attempt)
            continue
        if response.status_code >= 400:
            raise ModelRejected("模型服务暂不可用")
        return _read(response)
    raise ModelUnavailable("模型服务暂不可用") from last_error


def _read(response: httpx.Response) -> LLMResult:
    body = response.json()
    message = body["choices"][0]["message"]
    content = message.get("content") or ""
    if not content:
        content = _json_from(str(message.get("reasoning_content") or ""))
    usage = body.get("usage") or {}
    return LLMResult(
        content=content,
        tokens_in=int(usage.get("prompt_tokens") or 0),
        tokens_out=int(usage.get("completion_tokens") or 0),
    )


def _json_from(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return ""
    snippet = text[start : end + 1]
    try:
        json.loads(snippet)
    except json.JSONDecodeError:
        return ""
    return snippet
