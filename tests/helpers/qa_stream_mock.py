"""Shared qa_stream monkeypatch helpers (B7 retrieval_context kwarg)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from backend.graph.qa import QaEvent


def qa_stream_from_engine(engine: Any):
    """Build a qa_stream mock that forwards retrieval_context to GraphQaEngine.stream."""

    async def _mock_stream(
        paper_id: str,
        question: str,
        *,
        retrieval_context: Any = None,
        llm: Any = None,
    ) -> AsyncIterator[QaEvent]:
        _ = llm
        async for evt in engine.stream(paper_id, question, retrieval_context=retrieval_context):
            yield evt

    return _mock_stream
