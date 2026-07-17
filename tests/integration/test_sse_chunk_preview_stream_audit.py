# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B10 SSE event-level stream audit — no empty chunk text_preview mid-flight."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.qa_samples import STEM_DEMO_PAPER_ID, load_stem_demo_graph, seed_stem_qa_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.main import create_app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.rag.models import QuestionScale, RetrievalContext
from backend.rag.static_mock_vector_store import StaticMockVectorStore
from backend.schemas.chunk_preview import CHUNK_PREVIEW_STATE_MESSAGES, ChunkPreviewState
from backend.services.paper_service import get_paper_service
from backend.services.qa_retrieval import (
    VECTOR_RETRIEVAL_TIMEOUT_CODE,
    build_retrieval_context_with_fallback,
)
from httpx import ASGITransport, AsyncClient

from tests.graph.test_qa import _fake_llm
from tests.helpers.b10_qa_boundary import (
    audit_http_sse_chunk_citations,
    audit_qa_stream_chunk_citations,
    register_processing_paper,
)
from tests.helpers.vector_store_doubles import SlowGetChunkStore
from tests.rag.test_vector_store import _store_with_settings


async def _slow_retrieve(*_args, **_kwargs) -> RetrievalContext:
    await asyncio.sleep(0.05)
    return RetrievalContext(scale=QuestionScale.DETAIL, chunks=[])


@pytest.fixture
def stem_graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, GraphStore]:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_hybrid_retriever()
    reset_llm_client_cache()
    paper_id = STEM_DEMO_PAPER_ID
    seed_stem_qa_graph(graph_dir, paper_id=paper_id)
    return paper_id, GraphStore(base_dir=graph_dir)


async def _build_timeout_retrieval(
    paper_id: str,
    graph_store: GraphStore,
    *,
    vector_store: StaticMockVectorStore | SlowGetChunkStore,
) -> tuple[object, dict[str, str] | None]:
    retriever = HybridRetriever(vector_store=vector_store)
    retriever.retrieve = _slow_retrieve  # type: ignore[method-assign]
    bind_hybrid_retriever(retriever)
    paper_service = get_paper_service()
    result = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=graph_store,
        timeout_seconds=0.01,
    )
    assert result.warning_event is not None
    assert result.warning_event["code"] == VECTOR_RETRIEVAL_TIMEOUT_CODE
    return result.context, result.warning_event


@pytest.mark.asyncio
async def test_sse_chunk_event_never_leaks_empty_preview_on_l2_timeout(stem_graph_env: tuple[str, GraphStore]) -> None:
    """场景 ③：逐事件审计 qa_stream，L2 熔断也必须下发非空 timeout 占位符。"""
    paper_id, graph_store = stem_graph_env
    context, warning = await _build_timeout_retrieval(
        paper_id,
        graph_store,
        vector_store=SlowGetChunkStore(delay_seconds=0.5),
    )
    chunk_id = "stem-001:chunk:42"
    llm_text = f"细节见原文[CITE:chunk:{chunk_id}]。"
    timeout_marker = "[Vector retrieval timeout"

    inspected_at_yield: list[int] = []

    async def _stream():
        async for evt in qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
            retrieval_context=context,
            retrieval_warning=warning,
            llm=_fake_llm(llm_text, chunk_size=3),
        ):
            yield evt

    cites = await audit_qa_stream_chunk_citations(
        _stream(),
        expected_substrings=(timeout_marker,),
        on_chunk=lambda _data, idx: inspected_at_yield.append(idx),
    )

    assert len(cites) == 1
    assert cites[0]["preview_state"] in {
        ChunkPreviewState.L2_TIMEOUT,
        ChunkPreviewState.RETRIEVAL_TIMEOUT,
    }
    assert cites[0]["text_preview"] == CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.L2_TIMEOUT]
    assert inspected_at_yield, "chunk citation must be observed at yield time, not only after drain"


@pytest.mark.asyncio
async def test_sse_chunk_event_never_leaks_empty_preview_on_l2_rescue(stem_graph_env: tuple[str, GraphStore]) -> None:
    """场景 ①：流传输中途每个 chunk 事件都必须携带 ≤120 字符的真实预览。"""
    paper_id, graph_store = stem_graph_env
    context, warning = await _build_timeout_retrieval(
        paper_id,
        graph_store,
        vector_store=StaticMockVectorStore.load_default(),
    )
    chunk_id = "stem-001:chunk:42"
    llm_text = f"依据实验段落[CITE:chunk:{chunk_id}]，top-1 为 78.5%。"

    cites = await audit_qa_stream_chunk_citations(
        qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
            retrieval_context=context,
            retrieval_warning=warning,
            llm=_fake_llm(llm_text, chunk_size=4),
        ),
        expected_substrings=("78.5%",),
    )
    assert cites[0]["preview_state"] == ChunkPreviewState.READY
    assert len(cites[0]["text_preview"]) <= 120


@pytest.mark.asyncio
async def test_sse_chunk_event_never_leaks_empty_preview_on_cold_indexing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """场景 ②：PROCESSING + 无向量索引，流式 chunk 事件必须即时给出 indexing 占位符。"""
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_hybrid_retriever()
    reset_llm_client_cache()

    paper_id = "stem-002"
    graph = load_stem_demo_graph().model_copy(update={"paper_id": paper_id})
    graph_store = GraphStore(base_dir=graph_dir)
    graph_store.save(graph)

    paper_service = get_paper_service()
    register_processing_paper(paper_service, paper_id, preview_available=True)
    store, *_rest = _store_with_settings(None)
    store._paper_service = paper_service  # type: ignore[attr-defined]
    retriever = HybridRetriever(vector_store=store)
    bind_hybrid_retriever(retriever)

    retrieval = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=graph_store,
    )
    indexing_marker = "[Context indexing in progress"
    cites = await audit_qa_stream_chunk_citations(
        qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
            retrieval_context=retrieval.context,
            retrieval_warning=retrieval.warning_event,
            llm=_fake_llm("见[CITE:chunk:stem-002_chunk_1]。", chunk_size=2),
        ),
        expected_substrings=(indexing_marker,),
    )
    assert cites[0]["preview_state"] == ChunkPreviewState.INDEXING


@pytest.mark.asyncio
async def test_sse_chunk_event_never_leaks_empty_preview_on_hallucination(
    stem_graph_env: tuple[str, GraphStore],
) -> None:
    """场景 ④：幻觉 ID 在流式下发瞬间就必须是非空警告文案。"""
    paper_id, graph_store = stem_graph_env
    paper_service = get_paper_service()
    retriever = HybridRetriever(vector_store=StaticMockVectorStore.load_default())
    bind_hybrid_retriever(retriever)
    retrieval = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=graph_store,
    )
    cites = await audit_qa_stream_chunk_citations(
        qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？",
            retrieval_context=retrieval.context,
            retrieval_warning=retrieval.warning_event,
            llm=_fake_llm("引用[CITE:chunk:stem-001_chunk_99999]。", chunk_size=3),
        ),
        expected_substrings=("[Reference verification failed",),
    )
    assert cites[0]["preview_state"] == ChunkPreviewState.HALLUCINATED_ID


@pytest.fixture
async def timeout_http_client(
    stem_graph_env: tuple[str, GraphStore],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    paper_id, graph_store = stem_graph_env
    slow_store = SlowGetChunkStore(delay_seconds=0.5)
    retriever = HybridRetriever(vector_store=slow_store)
    retriever.retrieve = _slow_retrieve  # type: ignore[method-assign]
    bind_hybrid_retriever(retriever)

    llm_text = "细节见原文[CITE:chunk:stem-001:chunk:42]。"
    monkeypatch.setattr("backend.graph.qa.get_qa_llm_client", lambda: _fake_llm(llm_text, chunk_size=3))
    monkeypatch.setenv("QA_RETRIEVAL_TIMEOUT_SECONDS", "0.01")
    get_settings.cache_clear()
    reset_llm_client_cache()

    app = create_app()
    app.state.hybrid_retriever = retriever
    _ = paper_id, graph_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    reset_hybrid_retriever()


@pytest.mark.asyncio
async def test_http_raw_sse_stream_never_leaks_empty_chunk_preview(timeout_http_client: AsyncClient) -> None:
    """HTTP 原始字节流：按 frame 增量解析，确认 wire 层也无空 preview 泄漏。"""
    async with timeout_http_client.stream(
        "POST",
        "/api/v1/papers/stem-001/qa/stream",
        json={"question": "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        cites = await audit_http_sse_chunk_citations(
            response,
            expected_substrings=("[Vector retrieval timeout",),
        )

    assert len(cites) == 1
    assert cites[0]["text_preview"] != ""
