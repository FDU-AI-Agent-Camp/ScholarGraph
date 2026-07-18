# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B10 boundary ① — cold-start PROCESSING paper without vector index."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.qa_samples import load_stem_demo_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.main import create_app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.schemas.chunk_preview import CHUNK_PREVIEW_STATE_MESSAGES, ChunkPreviewState
from backend.services.paper_service import get_paper_service
from backend.services.qa_retrieval import build_retrieval_context_with_fallback
from httpx import ASGITransport, AsyncClient

from tests.graph.test_qa import _fake_llm
from tests.helpers.b10_qa_boundary import (
    chunk_citations,
    collect_qa_events,
    parse_sse_body,
    register_processing_paper,
)
from tests.rag.test_vector_store import _store_with_settings


@pytest.fixture
async def cold_start_qa_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """stem-002 PROCESSING + graph on disk + empty vector index (no active run)."""
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_llm_client_cache()

    paper_id = "stem-002"
    graph = load_stem_demo_graph().model_copy(update={"paper_id": paper_id})
    GraphStore(base_dir=graph_dir).save(graph)

    paper_service = get_paper_service()
    await register_processing_paper(paper_service, paper_id, preview_available=True)

    store, *_rest = _store_with_settings(None)
    store._paper_service = paper_service  # type: ignore[attr-defined]
    retriever = HybridRetriever(vector_store=store)
    bind_hybrid_retriever(retriever)

    llm_text = "实验细节见原文[CITE:chunk:stem-002_chunk_1]。"
    monkeypatch.setattr("backend.graph.qa.get_qa_llm_client", lambda: _fake_llm(llm_text))

    app = create_app()
    app.state.hybrid_retriever = retriever

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    reset_hybrid_retriever()
    get_paper_service.cache_clear()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_unindexed_processing_paper_chunk_citation_emits_indexing_placeholder_http(
    cold_start_qa_client: AsyncClient,
) -> None:
    """PROCESSING + no Chroma chunks → chunk cite must degrade to indexing state token."""
    async with cold_start_qa_client.stream(
        "POST",
        "/api/v1/papers/stem-002/qa/stream",
        json={"question": "ResNet-Light 在 ImageNet 上的准确率是多少？"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        body = ""
        async for chunk in response.aiter_text():
            body += chunk

    events = parse_sse_body(body)
    warning_events = [payload for event_name, payload in events if event_name == "warning"]
    assert len(warning_events) == 1, events
    assert warning_events[0]["code"] == "RAG_INDEX_NOT_READY"
    cites = chunk_citations(events)
    assert len(cites) == 1, events
    cite = cites[0]
    assert cite["chunk_id"] == "stem-002_chunk_1"
    assert cite["preview_state"] == ChunkPreviewState.INDEXING
    assert cite["text_preview"] == CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.INDEXING]
    assert cite["text_preview"] != ""


@pytest.mark.asyncio
async def test_unindexed_processing_paper_qa_stream_engine_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same cold-start contract via qa_stream() + build_retrieval_context_with_fallback."""
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_hybrid_retriever()
    reset_llm_client_cache()

    paper_id = "stem-002"
    graph = load_stem_demo_graph().model_copy(update={"paper_id": paper_id})
    store_graph = GraphStore(base_dir=graph_dir)
    store_graph.save(graph)

    paper_service = get_paper_service()
    await register_processing_paper(paper_service, paper_id, preview_available=True)

    vector_store, *_rest = _store_with_settings(None)
    vector_store._paper_service = paper_service  # type: ignore[attr-defined]
    retriever = HybridRetriever(vector_store=vector_store)
    bind_hybrid_retriever(retriever)

    retrieval = await build_retrieval_context_with_fallback(
        paper_id,
        "ResNet-Light 在 ImageNet 上的准确率是多少？",
        retriever=retriever,
        paper_service=paper_service,
        store=store_graph,
    )
    assert retrieval.context is not None
    assert retrieval.context.chunks == []
    assert retrieval.warning_event is not None
    assert retrieval.warning_event["code"] == "RAG_INDEX_NOT_READY"
    assert retrieval.context.metadata.index_ready is False

    llm_text = "依据原文[CITE:chunk:stem-002_chunk_1]。"
    events = await collect_qa_events(
        qa_stream(
            paper_id,
            "ResNet-Light 在 ImageNet 上的准确率是多少？",
            retrieval_context=retrieval.context,
            retrieval_warning=retrieval.warning_event,
            llm=_fake_llm(llm_text),
        ),
    )

    cites = chunk_citations(events)
    assert len(cites) == 1
    assert cites[0]["preview_state"] == ChunkPreviewState.INDEXING
    assert cites[0]["text_preview"] == CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.INDEXING]
