"""Deterministic LLM stand-ins when ``LLM_MODE=mock`` (no cloud API calls)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import BaseMessage

from backend.schemas.patrol_llm import PatrolSummaryOutput

MOCK_DISCLAIMER = "（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）"
MOCK_PATROL_PREFIX = "【Mock 巡检摘要】"
_MOCK_CHUNK_SIZE = 8
_NODE_ID_RE = re.compile(r"\[(n[\w-]+)\]")
_QUESTION_RE = re.compile(r"## 用户问题\s*\n(.+?)(?:\n## |\Z)", re.DOTALL)


class MockChunk:
    """Minimal stand-in for a LangChain AIMessageChunk."""

    def __init__(self, content: str) -> None:
        self.content = content


class MockStructuredOutput:
    """Fake ``with_structured_output`` runnable for patrol summaries."""

    def __init__(self, schema: type[Any]) -> None:
        self._schema = schema

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> Any:
        context = _human_content(messages)
        if self._schema is PatrolSummaryOutput:
            return PatrolSummaryOutput(summary=_mock_patrol_summary(context))
        return self._schema.model_validate({"summary": _mock_patrol_summary(context)})


class MockChat:
    """OpenAI-compatible chat surface backed by local templates."""

    def __init__(self, *, model: str) -> None:
        self.model_name = model

    async def astream(self, prompt: str) -> AsyncIterator[MockChunk]:
        text = _mock_qa_response(prompt)
        for index in range(0, len(text), _MOCK_CHUNK_SIZE):
            yield MockChunk(text[index : index + _MOCK_CHUNK_SIZE])

    def with_structured_output(self, schema: type[Any]) -> MockStructuredOutput:
        return MockStructuredOutput(schema)


def _human_content(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _mock_qa_response(prompt: str) -> str:
    question_match = _QUESTION_RE.search(prompt)
    question = question_match.group(1).strip() if question_match else "您的问题"
    node_ids = _NODE_ID_RE.findall(prompt)
    cite_target = node_ids[0] if node_ids else "n1"
    return f"根据知识图谱上下文，关于「{question}」可参考节点[CITE:{cite_target}]。{MOCK_DISCLAIMER}"


def _mock_patrol_summary(context: str) -> str:
    if not context.strip():
        return f"{MOCK_PATROL_PREFIX}当前无可用上下文，已回退模板逻辑。{MOCK_DISCLAIMER}"
    return (
        f"{MOCK_PATROL_PREFIX}基于两篇论文的图谱节点差异生成摘要（未调用华为云 LLM）。"
        f"上下文摘要：{context[:120]}… {MOCK_DISCLAIMER}"
    )
