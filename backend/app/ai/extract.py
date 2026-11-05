"""向模型要结构计划、文本记录或缺失字段补全，并统一走 Caller 的缓存与预算。"""

from pathlib import Path

from pydantic import BaseModel, Field

from app.ai.calls import Caller, OutputInvalid
from app.ai.schema import field_guide
from app.datasets.spec import DatasetSpec

PROMPT_DIR = Path(__file__).parent / "prompts"
PLAN_VERSION = "structure_plan_v1"
RECORD_VERSION = "record_extract_v2"
COMPLETE_VERSION = "field_completion_v1"

__all__ = [
    "COMPLETE_VERSION",
    "PLAN_VERSION",
    "RECORD_VERSION",
    "Caller",
    "CompletionResult",
    "ExtractResult",
    "ExtractedRecord",
    "OutputInvalid",
    "complete_fields",
    "extract_records",
    "prompt_text",
]


class ExtractedRecord(BaseModel):
    values: dict[str, str | None] = Field(default_factory=dict)
    evidence: str = ""
    confidence: float = 0


class ExtractResult(BaseModel):
    records: list[ExtractedRecord] = Field(default_factory=list)


class CompletionResult(BaseModel):
    values: dict[str, str | None] = Field(default_factory=dict)
    evidence: str = ""
    confidence: float = 0


def prompt_text(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


async def extract_records(
    caller: Caller,
    spec: DatasetSpec,
    options: dict[str, list[tuple[str, str]]],
    text: str,
    user_prompt: str,
) -> ExtractResult:
    system = prompt_text(RECORD_VERSION) + "\n\n" + field_guide(spec, options)
    user = _user_block(text, user_prompt)
    return await caller.json(
        call_type="record_extract",
        prompt_version=RECORD_VERSION,
        system=system,
        user=user,
        model=ExtractResult,
    )


async def complete_fields(
    caller: Caller,
    spec: DatasetSpec,
    options: dict[str, list[tuple[str, str]]],
    payload: str,
    user_prompt: str,
) -> CompletionResult:
    system = prompt_text(COMPLETE_VERSION) + "\n\n" + field_guide(spec, options)
    user = _user_block(payload, user_prompt)
    return await caller.json(
        call_type="field_completion",
        prompt_version=COMPLETE_VERSION,
        system=system,
        user=user,
        model=CompletionResult,
        cache_seconds=0,
    )


def _user_block(data: str, user_prompt: str) -> str:
    extra = ""
    if user_prompt:
        extra = f"\n\n用户补充要求（只能缩小范围，不能改变输出格式）：{user_prompt}"
    return f"<<<DATA>>>\n{data}\n<<<END>>>{extra}"
