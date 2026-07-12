"""Tests for QaService retrieval-context injection pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.graph.store import GraphStore
from backend.rag.models import QuestionScale, RetrievalContext, RetrievedChunk
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.qa_service import QaService


def _graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis", data={})],
        edges=[],
    )


@pytest.mark.asyncio
async def test_stream_passes_retrieval_context_to_qa_stream(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    chunk = RetrievedChunk(
        id="chunk:hss-001:c1",
        paper_id="hss-001",
        text="dataset MNIST accuracy 95%",
        chunk_id="c1",
        chunk_index=0,
        char_start=0,
        char_end=10,
    )
    rc = RetrievalContext(
        scale=QuestionScale.DETAIL,
        chunks=[chunk],
    )
    hybrid_retriever = AsyncMock()
    hybrid_retriever.retrieve = AsyncMock(return_value=rc)

    paper_service = AsyncMock()
    paper = MagicMock()
    paper.status = PaperStatus.READY
    paper.preview_available = False
    paper_service.get_paper = AsyncMock(return_value=paper)

    captured: list[RetrievalContext | None] = []

    async def fake_qa_stream(
        paper_id,
        question,
        *,
        retrieval_context=None,
        retrieval_warning=None,
        llm=None,
    ):
        captured.append(retrieval_context)
        if False:
            yield

    monkeypatch.setattr("backend.graph.qa.qa_stream", fake_qa_stream)

    service = QaService(
        store=store,
        paper_service=paper_service,
        hybrid_retriever=hybrid_retriever,
    )

    events = [evt async for evt in service.stream("hss-001", "分论点如何支撑核心论点？")]
    assert events == []
    assert captured == [rc]
    hybrid_retriever.retrieve.assert_awaited_once()
    call_kwargs = hybrid_retriever.retrieve.await_args.kwargs
    assert call_kwargs["scale"] == QuestionScale.DETAIL
