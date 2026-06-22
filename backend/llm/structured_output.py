"""Robust structured-output invocation that tolerates markdown-wrapped JSON."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from backend.llm.client import LlmClient

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)```\s*$", re.IGNORECASE)


def _strip_markdown_fences(raw: str) -> str:
    """Remove markdown code fences if the LLM wraps JSON in ```json ... ```."""
    stripped = raw.strip()
    match = _CODE_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_json(raw: str) -> str:
    """Return the first JSON object/array block found in ``raw``.

    Some models emit explanatory text before/after the JSON payload.
    """
    stripped = _strip_markdown_fences(raw)
    # If already clean JSON, return it.
    if stripped.startswith(("{", "[")):
        return stripped

    # Look for the first top-level brace/bracket and balance it.
    start = -1
    for idx, ch in enumerate(stripped):
        if ch in "{[":
            start = idx
            break
    if start == -1:
        return stripped

    open_char = stripped[start]
    close_char = "}" if open_char == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if ch == '"' and in_string:
            in_string = False
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return stripped[start : idx + 1]

    return stripped[start:]


def _parse_model_response(raw: str, schema: type[T], *, context: dict[str, Any] | None = None) -> T:
    """Parse raw LLM string into ``schema``, tolerating markdown wrappers.

    If the extracted JSON is truncated or malformed, attempt a local repair
    (bracket closure, escape fixes, etc.) before giving up. This avoids wasting
    API tokens on retries for trivially recoverable model output.
    """
    json_text = _extract_json(raw)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        try:
            from json_repair import loads as repair_loads

            data = repair_loads(json_text)
            if not isinstance(data, (dict, list)):
                raise ValueError("repaired content is not a JSON object or array")
            logger.warning(
                "json_repair_succeeded",
                extra={"original_preview": json_text[:200], "repaired_preview": json.dumps(data)[:200]},
            )
        except Exception as repair_exc:
            msg = f"Model returned non-JSON content: {raw[:200]}..."
            raise ValueError(msg) from repair_exc
    return schema.model_validate(data, context=context)


async def ainvoke_structured(
    client: LlmClient,
    schema: type[T],
    messages: list[BaseMessage],
    *,
    use_fallback_model: bool = False,
    context: dict[str, Any] | None = None,
) -> T:
    """Invoke the LLM and parse the response into ``schema``.

    Unlike LangChain's ``with_structured_output``, this helper strips markdown
    code fences, extracts the first JSON object, and locally repairs truncated
    JSON when possible, making it compatible with models that do not strictly
    follow OpenAI's JSON schema mode.
    """
    chat = client.fallback_chat if use_fallback_model and client.fallback_chat is not None else client.chat
    response = await chat.ainvoke(messages)
    content = response.content
    if not isinstance(content, str):
        content = str(content)
    return _parse_model_response(content, schema, context=context)
