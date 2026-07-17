# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Boundary matrix: HybridRetriever × StaticMockVectorStore interaction robustness."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from backend.graph.qa_samples import STEM_DEMO_PAPER_ID, load_stem_demo_graph
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale
from backend.rag.static_mock_vector_store import StaticMockVectorStore

from tests.conftest import REPO_ROOT

_HYDE_EMBEDDING: list[float] = [0.1, -0.2, 0.3, 0.0]
_STEM_QUERY = "ResNet-Light top-1 accuracy ImageNet learning rate"
_UNKNOWN_PAPER_IDS = (
    "stem-999",
    "hss-001",
    "evil-paper'; DROP TABLE--",
    "cross-paper-leak-attempt",
)


@pytest.fixture
def mock_store() -> StaticMockVectorStore:
    return StaticMockVectorStore.load(REPO_ROOT / "data" / "mock_vector_store.json")


@pytest.fixture
def retriever(mock_store: StaticMockVectorStore) -> HybridRetriever:
    return HybridRetriever(vector_store=mock_store)


@pytest.fixture
def stem_graph():
    return load_stem_demo_graph()


# ---------------------------------------------------------------------------
# Matrix row 1 — 传统检索降级：有效文本 + query_embedding=None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boundary_traditional_text_retrieval_ignores_none_embedding(mock_store: StaticMockVectorStore) -> None:
    chunks = await mock_store.query_chunks(
        _STEM_QUERY,
        paper_id=STEM_DEMO_PAPER_ID,
        top_k=2,
        query_embedding=None,
    )
    assert len(chunks) == 2
    assert all(chunk.paper_id == STEM_DEMO_PAPER_ID for chunk in chunks)
    assert any("78.5%" in chunk.text for chunk in chunks)


@pytest.mark.asyncio
async def test_boundary_traditional_hybrid_retriever_text_path(
    retriever: HybridRetriever,
    stem_graph: Any,
) -> None:
    context = await retriever.retrieve(
        STEM_DEMO_PAPER_ID,
        "What is the top-1 accuracy of ResNet-Light on ImageNet?",
        stem_graph,
        scale=QuestionScale.DETAIL,
        query_embedding=None,
    )
    assert context.chunks
    assert all(chunk.paper_id == STEM_DEMO_PAPER_ID for chunk in context.chunks)


# ---------------------------------------------------------------------------
# Matrix row 2 — 纯向量检索（HyDE 演进）：空文本 + 有效 embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boundary_hyde_empty_text_with_embedding_store_does_not_crash(
    mock_store: StaticMockVectorStore,
) -> None:
    """Store 层：参数解耦，空 query_text + embedding 不触发签名/ValueError。"""
    chunks = await mock_store.query_chunks(
        "",
        paper_id=STEM_DEMO_PAPER_ID,
        query_embedding=_HYDE_EMBEDDING,
    )
    assert isinstance(chunks, list)
    for chunk in chunks:
        assert chunk.paper_id == STEM_DEMO_PAPER_ID


@pytest.mark.asyncio
async def test_boundary_hyde_empty_text_entities_and_relations_store_safe(
    mock_store: StaticMockVectorStore,
) -> None:
    entities = await mock_store.query_entities(
        "",
        paper_id=STEM_DEMO_PAPER_ID,
        query_embedding=_HYDE_EMBEDDING,
    )
    relations = await mock_store.query_relations(
        "",
        paper_id=STEM_DEMO_PAPER_ID,
        query_embedding=_HYDE_EMBEDDING,
    )
    assert entities == []
    assert relations == []


@pytest.mark.asyncio
async def test_boundary_hyde_empty_question_retriever_skips_vector_store(
    retriever: HybridRetriever,
    stem_graph: Any,
) -> None:
    """Retriever 层：V1 空问题早返回，不向 store 分发（避免无意义 Chroma/Mock 调用）。"""
    store = retriever.vector_store
    assert store is not None
    store.query_chunks = AsyncMock(wraps=store.query_chunks)  # type: ignore[method-assign]

    context = await retriever.retrieve(
        STEM_DEMO_PAPER_ID,
        "   ",
        stem_graph,
        scale=QuestionScale.DETAIL,
        query_embedding=_HYDE_EMBEDDING,
    )

    assert context.chunks == []
    store.query_chunks.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_boundary_hyde_transform_supplies_text_while_embedding_present(
    retriever: HybridRetriever,
    stem_graph: Any,
) -> None:
    """HyDE 演进：query_transform 提供非空文本时，embedding 可并存且正常召回。"""
    context = await retriever.retrieve(
        STEM_DEMO_PAPER_ID,
        "",
        stem_graph,
        scale=QuestionScale.DETAIL,
        query_transform=lambda _q: _STEM_QUERY,
        query_embedding=_HYDE_EMBEDDING,
    )
    assert context.chunks
    assert all(chunk.paper_id == STEM_DEMO_PAPER_ID for chunk in context.chunks)


# ---------------------------------------------------------------------------
# Matrix row 3 — 关键字传参安全：显式 query_embedding=[...]
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ("query_chunks", "query_entities", "query_relations"))
async def test_boundary_keyword_query_embedding_unpacks_without_side_effects(
    mock_store: StaticMockVectorStore,
    method_name: str,
) -> None:
    method = getattr(mock_store, method_name)
    result = await method(
        _STEM_QUERY,
        paper_id=STEM_DEMO_PAPER_ID,
        top_k=3,
        query_embedding=_HYDE_EMBEDDING,
    )
    assert isinstance(result, list)

    baseline = await method(
        _STEM_QUERY,
        paper_id=STEM_DEMO_PAPER_ID,
        top_k=3,
        query_embedding=None,
    )
    if method_name == "query_chunks":
        assert len(result) == len(baseline)
        assert [chunk.chunk_id for chunk in result] == [chunk.chunk_id for chunk in baseline]
    else:
        assert result == baseline == []


@pytest.mark.asyncio
async def test_boundary_hybrid_retriever_keyword_embedding_forwarding(
    retriever: HybridRetriever,
    stem_graph: Any,
) -> None:
    store = retriever.vector_store
    assert store is not None
    store.query_chunks = AsyncMock(wraps=store.query_chunks)  # type: ignore[method-assign]

    await retriever.retrieve(
        STEM_DEMO_PAPER_ID,
        "ImageNet top-1 accuracy",
        stem_graph,
        scale=QuestionScale.DETAIL,
        query_embedding=_HYDE_EMBEDDING,
        top_k=2,
    )

    store.query_chunks.assert_awaited_once_with(  # type: ignore[attr-defined]
        "ImageNet top-1 accuracy",
        paper_id=STEM_DEMO_PAPER_ID,
        top_k=2,
        query_embedding=_HYDE_EMBEDDING,
    )


# ---------------------------------------------------------------------------
# Matrix row 4 — 越界 hard 过滤：不存在/恶意 paper_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("paper_id", _UNKNOWN_PAPER_IDS)
@pytest.mark.parametrize("method_name", ("query_chunks", "query_entities", "query_relations"))
async def test_boundary_unknown_paper_id_returns_empty_without_error(
    mock_store: StaticMockVectorStore,
    paper_id: str,
    method_name: str,
) -> None:
    assert await mock_store.exists(paper_id) is False
    method = getattr(mock_store, method_name)
    result = await method(
        _STEM_QUERY,
        paper_id=paper_id,
        query_embedding=_HYDE_EMBEDDING,
    )
    assert result == []


@pytest.mark.asyncio
@pytest.mark.parametrize("paper_id", _UNKNOWN_PAPER_IDS)
async def test_boundary_hybrid_retriever_unknown_paper_id_no_cross_leak(
    retriever: HybridRetriever,
    stem_graph: Any,
    paper_id: str,
) -> None:
    context = await retriever.retrieve(
        paper_id,
        "What is the top-1 accuracy on ImageNet?",
        stem_graph,
        scale=QuestionScale.DETAIL,
        query_embedding=_HYDE_EMBEDDING,
    )
    assert context.chunks == []
    assert context.entities == []
    assert context.relations == []


@pytest.mark.asyncio
async def test_boundary_valid_paper_never_returns_foreign_chunks(mock_store: StaticMockVectorStore) -> None:
    chunks = await mock_store.query_chunks(
        _STEM_QUERY,
        paper_id=STEM_DEMO_PAPER_ID,
        top_k=10,
        query_embedding=None,
    )
    assert chunks
    assert all(chunk.paper_id == STEM_DEMO_PAPER_ID for chunk in chunks)
    assert all("stem-001" in chunk.chunk_id for chunk in chunks)
