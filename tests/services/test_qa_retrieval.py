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
    VECTOR_RETRIEVAL_WARNING_SOURCE,
    VECTOR_STORE_UNAVAILABLE_CODE,
    VECTOR_STORE_UNAVAILABLE_MESSAGE,
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
        "source": VECTOR_RETRIEVAL_WARNING_SOURCE,
    }
    assert result.context is not None
    assert result.context.scale == QuestionScale.DETAIL
    assert result.context.chunks == []
    assert result.context.entities == []
    assert result.context.nodes


@pytest.mark.asyncio
async def test_vector_store_unavailable_falls_back_to_graph_only_with_warning(tmp_path) -> None:
    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(side_effect=ConnectionError("connection refused"))
    retriever = HybridRetriever(vector_store=vector_store)

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

    assert result.warning_event == {
        "code": VECTOR_STORE_UNAVAILABLE_CODE,
        "message": VECTOR_STORE_UNAVAILABLE_MESSAGE,
        "source": VECTOR_RETRIEVAL_WARNING_SOURCE,
    }
    assert result.context is not None
    assert result.context.scale == QuestionScale.DETAIL
    assert result.context.chunks == []
    assert result.context.nodes


@pytest.mark.asyncio
async def test_vector_store_unavailable_logs_underlying_exception_stack(tmp_path, caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="backend.services.qa_retrieval")

    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(side_effect=ConnectionError("connection refused"))
    retriever = HybridRetriever(vector_store=vector_store)

    paper_service = AsyncMock()
    paper = MagicMock()
    paper.status = PaperStatus.READY
    paper.preview_available = False
    paper_service.get_paper = AsyncMock(return_value=paper)

    await build_retrieval_context_with_fallback(
        "hss-001",
        "分论点如何支撑核心论点？",
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        timeout_seconds=1.0,
    )

    outage_logs = [
        record
        for record in caplog.records
        if "qa_retrieval_vector_store_unavailable" in record.getMessage()
    ]
    assert len(outage_logs) == 1
    assert outage_logs[0].exc_info is not None
    assert "ConnectionError" in caplog.text
    assert "connection refused" in caplog.text


@pytest.mark.asyncio
async def test_timeout_fallback_computes_subgraph_only_once(tmp_path) -> None:
    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    async def slow_retrieve(*args, **kwargs):
        await asyncio.sleep(0.05)
        from backend.rag.models import RetrievalContext

        return RetrievalContext(scale=QuestionScale.DETAIL)

    retriever = HybridRetriever(vector_store=None)
    retriever.retrieve = slow_retrieve  # type: ignore[method-assign]

    subgraph_calls = 0
    original_subgraph = retriever._graph_query.subgraph_for_question

    def counting_subgraph(graph, question):
        nonlocal subgraph_calls
        subgraph_calls += 1
        return original_subgraph(graph, question)

    retriever._graph_query.subgraph_for_question = counting_subgraph  # type: ignore[method-assign]

    paper_service = AsyncMock()
    paper = MagicMock()
    paper.status = PaperStatus.READY
    paper.preview_available = False
    paper_service.get_paper = AsyncMock(return_value=paper)

    await build_retrieval_context_with_fallback(
        "hss-001",
        "分论点如何支撑核心论点？",
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        timeout_seconds=0.01,
    )

    assert subgraph_calls == 1


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
