"""QA-D1 — single-paper QA must surface INDEX_NOT_READY like Patrol, not silent graph-only."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.graph.store import GraphStore
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale, RetrievalMetadata
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.qa_retrieval import (
    RAG_INDEX_NOT_READY_CODE,
    RAG_INDEX_NOT_READY_MESSAGE,
    VECTOR_RETRIEVAL_WARNING_SOURCE,
    build_retrieval_context_with_fallback,
)


def _graph(paper_id: str = "hss-001") -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis", data={})],
        edges=[],
    )


@pytest.mark.asyncio
async def test_hybrid_retrieve_marks_index_not_ready_metadata() -> None:
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=False)
    retriever = HybridRetriever(vector_store=vector_store)

    rc = await retriever.retrieve(
        "hss-001",
        "分论点如何支撑核心论点？",
        _graph(),
        scale=QuestionScale.DETAIL,
    )

    assert rc.metadata == RetrievalMetadata(index_ready=False, missing_reason="INDEX_NOT_READY")
    assert rc.chunks == []
    assert rc.nodes
    vector_store.query_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_build_retrieval_emits_rag_index_not_ready_warning_when_exists_false(tmp_path) -> None:
    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=False)
    retriever = HybridRetriever(vector_store=vector_store)

    paper_service = AsyncMock()
    paper = MagicMock()
    paper.status = PaperStatus.READY_WITH_WARNINGS
    paper.preview_available = True
    paper_service.get_paper = AsyncMock(return_value=paper)

    result = await build_retrieval_context_with_fallback(
        "hss-001",
        "分论点如何支撑核心论点？",
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        timeout_seconds=5.0,
    )

    assert result.warning_event is not None
    assert result.warning_event["code"] == RAG_INDEX_NOT_READY_CODE
    assert result.warning_event["code"] == "RAG_INDEX_NOT_READY"
    assert result.warning_event["message"] == RAG_INDEX_NOT_READY_MESSAGE
    assert result.warning_event["source"] == VECTOR_RETRIEVAL_WARNING_SOURCE
    assert result.context is not None
    assert result.context.metadata.index_ready is False
    assert result.context.metadata.missing_reason == "INDEX_NOT_READY"
    assert result.context.chunks == []
    assert result.context.nodes


@pytest.mark.asyncio
async def test_indexed_detail_retrieve_keeps_index_ready_true(tmp_path) -> None:
    store = GraphStore(base_dir=tmp_path)
    store.save(_graph())

    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=True)
    vector_store.query_entities = AsyncMock(return_value=[])
    vector_store.query_relations = AsyncMock(return_value=[])
    vector_store.query_chunks = AsyncMock(return_value=[])
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
        timeout_seconds=5.0,
    )

    assert result.warning_event is None
    assert result.context is not None
    assert result.context.metadata.index_ready is True
    assert result.context.metadata.missing_reason is None
