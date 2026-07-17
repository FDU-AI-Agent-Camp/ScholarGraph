# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Defensive boundaries: vector-store self-healing and concurrent request isolation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa_samples import M2_DEMO_PAPER_ID, STEM_DEMO_PAPER_ID, seed_m2_qa_graph, seed_stem_qa_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service
from backend.services.qa_retrieval import (
    VECTOR_RETRIEVAL_WARNING_SOURCE,
    VECTOR_STORE_UNAVAILABLE_CODE,
    build_retrieval_context_with_fallback,
)
from httpx import ASGITransport, AsyncClient

from tests.graph.test_qa import _fake_llm
from tests.helpers.b10_qa_boundary import parse_sse_body
from tests.helpers.vector_store_doubles import FlakyExistsVectorStore, PaperScopedFaultVectorStore

STEM_DETAIL_QUESTION = "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？"
HSS_DETAIL_QUESTION = "分论点如何支撑核心论点？"


@pytest.fixture
def dual_paper_qa_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, GraphStore]:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_hybrid_retriever()
    reset_llm_client_cache()
    seed_stem_qa_graph(graph_dir, paper_id=STEM_DEMO_PAPER_ID)
    seed_m2_qa_graph(graph_dir, paper_id=M2_DEMO_PAPER_ID)
    return graph_dir, GraphStore(base_dir=graph_dir)


@pytest.fixture
async def dual_paper_http_client(
    dual_paper_qa_env: tuple[Path, GraphStore],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    _graph_dir, _graph_store = dual_paper_qa_env
    retriever = HybridRetriever(vector_store=FlakyExistsVectorStore(fail_count=0))
    bind_hybrid_retriever(retriever)

    for paper_id in (STEM_DEMO_PAPER_ID, M2_DEMO_PAPER_ID):
        paper = await get_paper_service().get_paper(paper_id)
        assert paper.status == PaperStatus.READY

    monkeypatch.setattr(
        "backend.graph.qa.get_qa_llm_client",
        lambda: _fake_llm("依据证据[CITE:n_claim][CITE:n1]作答。", chunk_size=4),
    )
    reset_llm_client_cache()
    app.state.hybrid_retriever = retriever

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    reset_hybrid_retriever()


def _warning_codes(events: list[tuple[str, dict]]) -> list[str]:
    return [payload["code"] for name, payload in events if name == "warning"]


@pytest.mark.asyncio
async def test_vector_store_recovers_full_retrieval_after_transient_outage(
    dual_paper_qa_env: tuple[Path, GraphStore],
) -> None:
    """正常 → 闪断 → 恢复：后续请求自动重连，warning 消失且向量召回恢复。"""
    graph_dir, graph_store = dual_paper_qa_env
    flaky_store = FlakyExistsVectorStore(fail_count=1)
    retriever = HybridRetriever(vector_store=flaky_store)
    paper_service = get_paper_service()

    outage = await build_retrieval_context_with_fallback(
        STEM_DEMO_PAPER_ID,
        STEM_DETAIL_QUESTION,
        retriever=retriever,
        paper_service=paper_service,
        store=graph_store,
        timeout_seconds=2.0,
    )
    assert outage.warning_event is not None
    assert outage.warning_event["code"] == VECTOR_STORE_UNAVAILABLE_CODE
    assert outage.warning_event["source"] == VECTOR_RETRIEVAL_WARNING_SOURCE
    assert outage.context is not None
    assert outage.context.chunks == []

    recovered = await build_retrieval_context_with_fallback(
        STEM_DEMO_PAPER_ID,
        STEM_DETAIL_QUESTION,
        retriever=retriever,
        paper_service=paper_service,
        store=graph_store,
        timeout_seconds=2.0,
    )
    assert recovered.warning_event is None
    assert recovered.context is not None
    assert recovered.context.chunks
    assert any("78.5%" in chunk.text for chunk in recovered.context.chunks)


@pytest.mark.asyncio
async def test_concurrent_faulty_and_healthy_papers_stay_isolated(
    dual_paper_qa_env: tuple[Path, GraphStore],
) -> None:
    """并发请求：故障 paper 降级发 warning，健康 paper 完整向量召回且互无污染。"""
    graph_dir, graph_store = dual_paper_qa_env
    scoped_store = PaperScopedFaultVectorStore(fault_paper_ids=frozenset({STEM_DEMO_PAPER_ID}))
    retriever = HybridRetriever(vector_store=scoped_store)
    paper_service = get_paper_service()

    async def _retrieve(paper_id: str, question: str):
        return await build_retrieval_context_with_fallback(
            paper_id,
            question,
            retriever=retriever,
            paper_service=paper_service,
            store=graph_store,
            timeout_seconds=2.0,
        )

    faulty_result, healthy_result = await asyncio.gather(
        _retrieve(STEM_DEMO_PAPER_ID, STEM_DETAIL_QUESTION),
        _retrieve(M2_DEMO_PAPER_ID, HSS_DETAIL_QUESTION),
    )

    assert faulty_result.warning_event is not None
    assert faulty_result.warning_event["code"] == VECTOR_STORE_UNAVAILABLE_CODE
    assert faulty_result.context is not None
    assert faulty_result.context.chunks == []

    assert healthy_result.warning_event is None
    assert healthy_result.context is not None
    assert healthy_result.context.chunks
    assert all(chunk.paper_id == M2_DEMO_PAPER_ID for chunk in healthy_result.context.chunks)


@pytest.mark.asyncio
async def test_sse_self_heals_after_transient_vector_store_outage(
    dual_paper_http_client: AsyncClient,
) -> None:
    """HTTP 全链路：闪断请求带 warning，恢复后后续 SSE 不再下发 warning。"""
    flaky_store = FlakyExistsVectorStore(fail_count=1)
    retriever = HybridRetriever(vector_store=flaky_store)
    bind_hybrid_retriever(retriever)
    app.state.hybrid_retriever = retriever

    outage_response = await dual_paper_http_client.post(
        f"/api/v1/papers/{STEM_DEMO_PAPER_ID}/qa/stream",
        json={"question": STEM_DETAIL_QUESTION},
        headers={"Accept": "text/event-stream"},
    )
    assert outage_response.status_code == 200
    outage_events = parse_sse_body(outage_response.text)
    assert outage_events[0][0] == "warning"
    assert VECTOR_STORE_UNAVAILABLE_CODE in _warning_codes(outage_events)

    recovered_response = await dual_paper_http_client.post(
        f"/api/v1/papers/{STEM_DEMO_PAPER_ID}/qa/stream",
        json={"question": STEM_DETAIL_QUESTION},
        headers={"Accept": "text/event-stream"},
    )
    assert recovered_response.status_code == 200
    recovered_events = parse_sse_body(recovered_response.text)
    assert "warning" not in [name for name, _ in recovered_events]
    assert recovered_events[0][0] == "message"
    assert recovered_events[-1][0] == "done"


@pytest.mark.asyncio
async def test_sse_concurrent_fault_does_not_pollute_healthy_paper(
    dual_paper_http_client: AsyncClient,
) -> None:
    """并发 HTTP：stem-001 降级 warning 不影响 hss-001 正常向量问答。"""
    scoped_store = PaperScopedFaultVectorStore(fault_paper_ids=frozenset({STEM_DEMO_PAPER_ID}))
    retriever = HybridRetriever(vector_store=scoped_store)
    bind_hybrid_retriever(retriever)
    app.state.hybrid_retriever = retriever

    async def _post_sse(paper_id: str, question: str) -> list[tuple[str, dict]]:
        response = await dual_paper_http_client.post(
            f"/api/v1/papers/{paper_id}/qa/stream",
            json={"question": question},
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200
        return parse_sse_body(response.text)

    faulty_events, healthy_events = await asyncio.gather(
        _post_sse(STEM_DEMO_PAPER_ID, STEM_DETAIL_QUESTION),
        _post_sse(M2_DEMO_PAPER_ID, HSS_DETAIL_QUESTION),
    )

    assert faulty_events[0][0] == "warning"
    assert VECTOR_STORE_UNAVAILABLE_CODE in _warning_codes(faulty_events)
    assert "error" not in [name for name, _ in faulty_events]

    assert "warning" not in [name for name, _ in healthy_events]
    assert healthy_events[0][0] == "message"
    assert healthy_events[-1][0] == "done"
    assert "error" not in [name for name, _ in healthy_events]
