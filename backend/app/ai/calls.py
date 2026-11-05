"""模型调用的统一入口：缓存、预算、用量统计和输出校验。"""

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.ai.client import LLMClient, LLMResult
from app.core.config import resolved_ai, settings
from app.models.common import uuid_hex

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ingestion import IngestTask

logger = logging.getLogger(__name__)
_EXCERPT = 400


class BudgetExceeded(Exception):
    """任务级模型调用预算用尽。"""


class OutputInvalid(Exception):
    pass


class Caller:
    def __init__(
        self,
        session: "AsyncSession",
        task: "IngestTask",
        client: LLMClient,
        *,
        budget: int,
        cache_enabled: bool,
    ) -> None:
        self.session = session
        self.task = task
        self.client = client
        self.budget = budget
        self.cache_enabled = cache_enabled
        self.breakdown: dict[str, dict[str, int]] = {}

    async def json[T: BaseModel](
        self,
        *,
        call_type: str,
        prompt_version: str,
        system: str,
        user: str,
        model: type[T],
        cache_seconds: int = 86400,
        check: Callable[[T], None] | None = None,
    ) -> T:
        """调用模型并解析为 model。

        `check` 用于语义校验（例如计划里必须至少有一张数据表）。不通过的输出
        既不会写缓存也不会命中缓存，避免一次截断的输出把后续重试全部堵死。
        """
        _provider, _base, _key, model_name = resolved_ai()
        key = hashlib.sha256(
            f"{call_type}|{prompt_version}|{model_name}|{system}|{user}".encode()
        ).hexdigest()[:64]
        if self.cache_enabled and cache_seconds > 0:
            cached = await self._cached(key, model, check)
            if cached is not None:
                self._note(call_type, LLMResult(content="", tokens_in=0, tokens_out=0), cached=True)
                return cached
        if self.task.llm_calls >= self.budget:
            raise BudgetExceeded(f"{call_type} 超出任务调用预算")
        result, parsed = await self._call(system, user, model, check, label=call_type)
        self.task.llm_calls += 1
        self.task.tokens_in += result.tokens_in
        self.task.tokens_out += result.tokens_out
        self._note(call_type, result, cached=False)
        if self.cache_enabled and cache_seconds > 0:
            from app.models.ingestion import AiCallCache

            now = datetime.now(UTC)
            self.session.add(
                AiCallCache(
                    id=uuid_hex(),
                    cache_key=key,
                    call_type=call_type,
                    prompt_version=prompt_version,
                    model=model_name,
                    output=parsed.model_dump(mode="json"),
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    created_at=now,
                    expires_at=now + timedelta(seconds=cache_seconds),
                )
            )
        return parsed

    async def _cached[T: BaseModel](
        self, key: str, model: type[T], check: Callable[[T], None] | None = None
    ) -> T | None:
        from app.models.ingestion import AiCallCache

        row = await self.session.scalar(
            select(AiCallCache).where(
                AiCallCache.cache_key == key,
                AiCallCache.expires_at > datetime.now(UTC),
            )
        )
        if row is None:
            return None
        try:
            parsed = model.model_validate(row.output)
        except ValidationError:
            return None
        if check is not None:
            try:
                check(parsed)
            except ValueError:
                # 旧版本写进缓存的无效输出：删掉，让本次调用重新请求模型。
                await self.session.delete(row)
                await self.session.flush()
                return None
        return parsed

    async def _call[T: BaseModel](
        self,
        system: str,
        user: str,
        model: type[T],
        check: Callable[[T], None] | None = None,
        *,
        label: str,
    ) -> tuple[LLMResult, T]:
        last = ""
        result: LLMResult | None = None
        for attempt in range(2):
            prompt = user
            if last:
                prompt = f"{user}\n\n上次输出无法解析：{last}\n请只返回合法 JSON。"
            result = await self.client.complete(system=system, user=prompt)
            try:
                parsed = model.model_validate(json.loads(result.content or "{}"))
            except (json.JSONDecodeError, ValidationError) as exc:
                last = str(exc)[:800] or exc.__class__.__name__
                self._log_bad_output(label, attempt, result, last)
                continue
            if check is not None:
                try:
                    check(parsed)
                except ValueError as exc:
                    last = str(exc) or exc.__class__.__name__
                    self._log_bad_output(label, attempt, result, last)
                    continue
            return result, parsed
        raise OutputInvalid(last or "模型输出无法解析")

    def _log_bad_output(self, label: str, attempt: int, result: LLMResult, reason: str) -> None:
        """记录解析失败的现场。输出被截断和格式写错在日志里很好区分。

        原文片段可能含业务数据，可用 LOG_FAILED_MODEL_OUTPUT=false 关掉。
        """
        content = result.content or ""
        excerpt = "-"
        if settings.log_failed_model_output and content:
            if len(content) <= _EXCERPT * 2:
                excerpt = content
            else:
                omitted = len(content) - _EXCERPT * 2
                excerpt = f"{content[:_EXCERPT]}……省略 {omitted} 字符……{content[-_EXCERPT:]}"
        logger.warning(
            "模型输出无法解析 task=%s call=%s attempt=%s tokens_out=%s "
            "content_len=%s reason=%s content=%s",
            self.task.id,
            label,
            attempt,
            result.tokens_out,
            len(content),
            reason,
            excerpt,
        )

    def _note(self, call_type: str, result: LLMResult, *, cached: bool) -> None:
        usage = self.breakdown.setdefault(
            call_type, {"calls": 0, "cached": 0, "tokens_in": 0, "tokens_out": 0}
        )
        usage["cached" if cached else "calls"] += 1
        usage["tokens_in"] += result.tokens_in
        usage["tokens_out"] += result.tokens_out
        self.task.usage_breakdown = dict(self.breakdown)
