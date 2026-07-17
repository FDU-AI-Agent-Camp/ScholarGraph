# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""API route-layer QA scale defense and hybrid retrieval shadow verification."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.rag.models import QuestionScale
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _bind_minimal_hybrid_retriever_for_api_tests() -> AsyncIterator[None]:
    """Prevent accidental Chroma init when FastAPI resolves retriever dependency."""
    retriever = HybridRetriever(vector_store=None)
    bind_hybrid_retriever(retriever)
    app.state.hybrid_retriever = retriever
    yield
    reset_hybrid_retriever()
    if hasattr(app.state, "hybrid_retriever"):
        delattr(app.state, "hybrid_retriever")


@pytest.fixture
def qa_route_graph_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    store = GraphStore(base_dir=tmp_path)
    store.save(
        UnifiedPaperGraph(
            paper_id="hss-001",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n1", label="核心论点", type="Thesis", data={}),
                GraphNode(id="n2", label="分论点", type="SubArgument", data={}),
            ],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n2",
                    target="n1",
                    label="SUB_ARGUMENT_OF",
                    type="SUB_ARGUMENT_OF",
                ),
            ],
        ),
    )
    return store


def _mock_vector_store() -> AsyncMock:
    store = AsyncMock()
    store.exists = AsyncMock(return_value=True)
    store.query_entities = AsyncMock(return_value=[])
    store.query_relations = AsyncMock(return_value=[])
    store.query_chunks = AsyncMock(return_value=[])
    return store


@pytest.fixture
def spy_hybrid_retriever() -> AsyncIterator[HybridRetriever]:
    """HybridRetriever with vector store + spies on retrieve and ``_retrieve_vectors``."""
    vector_store = _mock_vector_store()
    retriever = HybridRetriever(vector_store=vector_store)
    vector_spy = AsyncMock(wraps=retriever._retrieve_vectors)
    retriever._retrieve_vectors = vector_spy  # type: ignore[method-assign]
    retrieve_spy = AsyncMock(wraps=retriever.retrieve)
    retriever.retrieve = retrieve_spy  # type: ignore[method-assign]
    retriever._vector_spy = vector_spy  # type: ignore[attr-defined]
    retriever._retrieve_spy = retrieve_spy  # type: ignore[attr-defined]

    bind_hybrid_retriever(retriever)
    app.state.hybrid_retriever = retriever
    yield retriever
    reset_hybrid_retriever()
    if hasattr(app.state, "hybrid_retriever"):
        delattr(app.state, "hybrid_retriever")


# ---------------------------------------------------------------------------
# A. CROSS_PAPER 熔断拦截
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qa_stream_cross_paper_returns_400_with_patrol_guide(
    api_client: AsyncClient,
    qa_route_graph_store: GraphStore,
) -> None:
    """POST /qa/stream with cross-paper compare phrasing must fuse before SSE."""
    _ = qa_route_graph_store
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "compare to other models"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Patrol" in detail or "跨论文巡航" in detail


# ---------------------------------------------------------------------------
# B. 动态接线影子测试（Shadow Verification）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qa_stream_summary_shadow_skips_vector_retrieval_branch(
    api_client: AsyncClient,
    qa_route_graph_store: GraphStore,
    spy_hybrid_retriever: HybridRetriever,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SUMMARY questions must not invoke ``HybridRetriever._retrieve_vectors``."""
    _ = qa_route_graph_store
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "这篇论文的主要贡献是什么？"},
    )
    assert response.status_code == 200
    vector_spy: AsyncMock = spy_hybrid_retriever._vector_spy  # type: ignore[attr-defined]
    retrieve_spy: AsyncMock = spy_hybrid_retriever._retrieve_spy  # type: ignore[attr-defined]
    assert vector_spy.call_count == 0
    assert retrieve_spy.await_args is not None
    assert retrieve_spy.await_args.kwargs["scale"] == QuestionScale.SUMMARY


@pytest.mark.asyncio
async def test_qa_stream_detail_shadow_activates_vector_retrieval_branch(
    api_client: AsyncClient,
    qa_route_graph_store: GraphStore,
    spy_hybrid_retriever: HybridRetriever,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DETAIL questions must invoke hybrid vector retrieval exactly once."""
    _ = qa_route_graph_store
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "表格 2 里面的准确率是多少？"},
    )
    assert response.status_code == 200
    vector_spy: AsyncMock = spy_hybrid_retriever._vector_spy  # type: ignore[attr-defined]
    retrieve_spy: AsyncMock = spy_hybrid_retriever._retrieve_spy  # type: ignore[attr-defined]
    assert vector_spy.call_count == 1
    assert retrieve_spy.await_args is not None
    assert retrieve_spy.await_args.kwargs["scale"] == QuestionScale.DETAIL
