"""Retrieval timeout and graph-only fallback for QA."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.graph.store import GraphStore
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale, RetrievedChunk
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.qa_retrieval import (
    VECTOR_RETRIEVAL_TIMEOUT_CODE,
    VECTOR_RETRIEVAL_TIMEOUT_MESSAGE,
    build_retrieval_context_with_fallback,
)


def _graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis", data={})],
        edges=[],
    )


@pytest.mark.asyncio
async def test_retrieval_timeout_falls_back_to_graph_only(tmp_path) -> None:
    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    async def slow_retrieve(*args, **kwargs):
        await asyncio.sleep(0.05)
        chunk = RetrievedChunk(
            id="chunk:hss-001:c1",
            paper_id="hss-001",
            text="should not appear",
            chunk_id="c1",
            chunk_index=0,
            char_start=0,
            char_end=4,
        )
        from backend.rag.models import RetrievalContext

        return RetrievalContext(scale=QuestionScale.DETAIL, chunks=[chunk])

    retriever = HybridRetriever(vector_store=None)
    retriever.retrieve = slow_retrieve  # type: ignore[method-assign]

    paper_service = AsyncMock()
    paper = MagicMock()
    paper.status = PaperStatus.READY
    paper.preview_available = False
    paper_service.get_paper = AsyncMock(return_value=paper)

    result = await build_retrieval_context_with_fallback(
        "hss-001",
        "分论点如何支撑核心论点？",
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        timeout_seconds=0.01,
    )

    assert result.warning_event == {
        "code": VECTOR_RETRIEVAL_TIMEOUT_CODE,
        "message": VECTOR_RETRIEVAL_TIMEOUT_MESSAGE,
    }
    assert result.context is not None
    assert result.context.scale == QuestionScale.DETAIL
    assert result.context.chunks == []
    assert result.context.entities == []
    assert result.context.nodes


@pytest.mark.asyncio
async def test_retrieval_success_has_no_warning(tmp_path) -> None:
    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    chunk = RetrievedChunk(
        id="chunk:hss-001:c1",
        paper_id="hss-001",
        text="vector hit",
        chunk_id="c1",
        chunk_index=0,
        char_start=0,
        char_end=4,
    )
    retriever = AsyncMock()
    from backend.rag.models import RetrievalContext

    retriever.retrieve = AsyncMock(return_value=RetrievalContext(scale=QuestionScale.DETAIL, chunks=[chunk]))

    paper_service = AsyncMock()
    paper = MagicMock()
    paper.status = PaperStatus.READY
    paper.preview_available = False
    paper_service.get_paper = AsyncMock(return_value=paper)

    result = await build_retrieval_context_with_fallback(
        "hss-001",
        "分论点如何支撑核心论点？",
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        timeout_seconds=1.0,
    )

    assert result.warning_event is None
    assert result.context is not None
    assert result.context.chunks == [chunk]
