"""Native structured-output invocation for QA Judge (OpenAI JSON schema mode)."""

from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from backend.llm.client import LlmClient
from backend.rag.models import JudgeSchema

T = TypeVar("T", bound=BaseModel)


async def invoke_judge_structured_output(
    client: LlmClient,
    messages: list[BaseMessage],
    *,
    schema: type[T] = JudgeSchema,
) -> T:
    """Invoke Judge via ``with_structured_output`` — no markdown/regex JSON parsing."""
    structured = client.chat.with_structured_output(schema)  # type: ignore[union-attr]
    result = await structured.ainvoke(messages)
    if isinstance(result, schema):
        return result
    return schema.model_validate(result)
