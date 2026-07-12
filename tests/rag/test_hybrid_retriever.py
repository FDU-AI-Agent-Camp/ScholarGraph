"""Tests for HybridRetriever scale branching and vector recall."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.graph.query import GraphQuery
from backend.rag.exceptions import VectorStoreUnavailableError
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale, RetrievedChunk
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

logger = logging.getLogger("backend.rag.hybrid_retriever")

_INDEX_MISSING_SCALES = (QuestionScale.DETAIL, QuestionScale.VERIFICATION)
_EXISTS_FAULTS = (ConnectionError("chroma unreachable"), TimeoutError("chroma probe timed out"))


def _sample_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
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
    )


def _sample_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        id="chunk:hss-001:c1",
        paper_id="hss-001",
        text="Institution text about path dependence.",
        chunk_id="c1",
        chunk_index=0,
        char_start=0,
        char_end=42,
        page_start=3,
    )


@pytest.mark.asyncio
async def test_summary_scale_skips_vector_queries() -> None:
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=True)
    retriever = HybridRetriever(vector_store=vector_store)

    rc = await retriever.retrieve(
        "hss-001",
        "这篇论文做了什么？",
        _sample_graph(),
        scale=QuestionScale.SUMMARY,
    )

    assert rc.scale == QuestionScale.SUMMARY
    assert rc.nodes
    assert rc.chunks == []
    vector_store.query_chunks.assert_not_called()
    vector_store.query_entities.assert_not_called()
    vector_store.query_relations.assert_not_called()


@pytest.mark.asyncio
async def test_detail_scale_queries_all_vector_collections() -> None:
    chunk = _sample_chunk()
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=True)
    vector_store.query_entities = AsyncMock(return_value=[])
    vector_store.query_relations = AsyncMock(return_value=[])
    vector_store.query_chunks = AsyncMock(return_value=[chunk])
    retriever = HybridRetriever(vector_store=vector_store)

    rc = await retriever.retrieve(
        "hss-001",
        "分论点如何支撑核心论点？",
        _sample_graph(),
        scale=QuestionScale.DETAIL,
    )

    assert rc.scale == QuestionScale.DETAIL
    assert rc.chunks == [chunk]
    vector_store.query_chunks.assert_awaited_once_with(
        "分论点如何支撑核心论点？",
        paper_id="hss-001",
        top_k=None,
        query_embedding=None,
    )
    vector_store.query_entities.assert_awaited_once()
    vector_store.query_relations.assert_awaited_once()


# ---------------------------------------------------------------------------
# C5 输入矩阵 — 业务不存在 vs 基础设施故障
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("scale", _INDEX_MISSING_SCALES)
async def test_matrix_index_missing_returns_empty_vectors_without_error_logs(
    scale: QuestionScale,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """业务边界：exists() 正常返回 False → 安静空召回，图谱子图仍可用。"""
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=False)
    retriever = HybridRetriever(vector_store=vector_store)

    caplog.set_level(logging.ERROR, logger="backend.rag.hybrid_retriever")

    rc = await retriever.retrieve(
        "hss-001",
        "分论点如何支撑核心论点？",
        _sample_graph(),
        scale=scale,
    )

    assert rc.scale == scale
    assert rc.chunks == []
    assert rc.entities == []
    assert rc.relations == []
    assert rc.nodes
    assert rc.edges
    vector_store.exists.assert_awaited_once_with("hss-001")
    vector_store.query_chunks.assert_not_called()
    vector_store.query_entities.assert_not_called()
    vector_store.query_relations.assert_not_called()
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", _EXISTS_FAULTS)
async def test_matrix_exists_infrastructure_fault_raises_domain_error(fault: BaseException) -> None:
    """故障注入：exists() 抛连接/超时异常 → 方案 A 上抛 VectorStoreUnavailableError。"""
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(side_effect=fault)
    retriever = HybridRetriever(vector_store=vector_store)

    with pytest.raises(VectorStoreUnavailableError, match="index check failed") as exc_info:
        await retriever.retrieve(
            "hss-001",
            "分论点如何支撑核心论点？",
            _sample_graph(),
            scale=QuestionScale.DETAIL,
        )

    assert exc_info.value.paper_id == "hss-001"
    assert exc_info.value.cause is fault
    vector_store.query_chunks.assert_not_called()
    vector_store.query_entities.assert_not_called()
    vector_store.query_relations.assert_not_called()


@pytest.mark.asyncio
async def test_detail_scale_query_failure_raises_vector_store_unavailable() -> None:
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=True)
    vector_store.query_entities = AsyncMock(side_effect=RuntimeError("chroma query failed"))
    vector_store.query_relations = AsyncMock(return_value=[])
    vector_store.query_chunks = AsyncMock(return_value=[])
    retriever = HybridRetriever(vector_store=vector_store)

    with pytest.raises(VectorStoreUnavailableError, match="vector retrieval failed"):
        await retriever.retrieve(
            "hss-001",
            "分论点如何支撑核心论点？",
            _sample_graph(),
            scale=QuestionScale.DETAIL,
        )


@pytest.mark.asyncio
async def test_detail_scale_without_index_returns_empty_vectors() -> None:
    """向后兼容薄包装：委托矩阵用例覆盖 DETAIL + exists=False。"""
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=False)
    retriever = HybridRetriever(vector_store=vector_store)

    rc = await retriever.retrieve(
        "hss-001",
        "分论点如何支撑核心论点？",
        _sample_graph(),
        scale=QuestionScale.DETAIL,
    )

    assert rc.scale == QuestionScale.DETAIL
    assert rc.chunks == []
    vector_store.query_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_query_transform_rewrites_embedding_text() -> None:
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=True)
    vector_store.query_entities = AsyncMock(return_value=[])
    vector_store.query_relations = AsyncMock(return_value=[])
    vector_store.query_chunks = AsyncMock(return_value=[])
    retriever = HybridRetriever(vector_store=vector_store)

    await retriever.retrieve(
        "hss-001",
        "原始问题",
        _sample_graph(),
        scale=QuestionScale.VERIFICATION,
        query_transform=lambda _q: "改写后的问题",
    )

    vector_store.query_chunks.assert_awaited_once_with(
        "改写后的问题",
        paper_id="hss-001",
        top_k=None,
        query_embedding=None,
    )


@pytest.mark.asyncio
async def test_detail_scale_passes_query_embedding_to_vector_store() -> None:
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=True)
    vector_store.query_entities = AsyncMock(return_value=[])
    vector_store.query_relations = AsyncMock(return_value=[])
    vector_store.query_chunks = AsyncMock(return_value=[])
    retriever = HybridRetriever(vector_store=vector_store)
    embedding = [0.1, 0.2, 0.3]

    await retriever.retrieve(
        "hss-001",
        "数据集是什么？",
        _sample_graph(),
        scale=QuestionScale.DETAIL,
        query_embedding=embedding,
    )

    vector_store.query_chunks.assert_awaited_once_with(
        "数据集是什么？",
        paper_id="hss-001",
        top_k=None,
        query_embedding=embedding,
    )


@pytest.mark.asyncio
async def test_graph_subgraph_populated_via_graph_query() -> None:
    subgraph = {"nodes": [{"id": "n1"}], "edges": []}
    graph_query = MagicMock(spec=GraphQuery)
    graph_query.subgraph_for_question.return_value = subgraph
    retriever = HybridRetriever(graph_query=graph_query, vector_store=None)

    rc = await retriever.retrieve(
        "hss-001",
        "核心论点是什么？",
        _sample_graph(),
        scale=QuestionScale.SUMMARY,
    )

    assert rc.nodes == subgraph["nodes"]
    assert rc.edges == subgraph["edges"]
    graph_query.subgraph_for_question.assert_called_once()


@pytest.mark.asyncio
async def test_detail_scale_passes_top_k_to_vector_store() -> None:
    chunk = _sample_chunk()
    vector_store = AsyncMock()
    vector_store.exists = AsyncMock(return_value=True)
    vector_store.query_entities = AsyncMock(return_value=[])
    vector_store.query_relations = AsyncMock(return_value=[])
    vector_store.query_chunks = AsyncMock(return_value=[chunk])
    retriever = HybridRetriever(vector_store=vector_store)

    await retriever.retrieve(
        "hss-001",
        "分论点如何支撑核心论点？",
        _sample_graph(),
        scale=QuestionScale.DETAIL,
        top_k=7,
    )

    vector_store.query_chunks.assert_awaited_once_with(
        "分论点如何支撑核心论点？",
        paper_id="hss-001",
        top_k=7,
        query_embedding=None,
    )
