# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""E2E HTTP tests: detail QA stream recalls vector chunks via HybridRetriever."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.main import create_app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.rag.models import PaperChunk
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient
from tests.graph.test_qa import _fake_llm
from tests.helpers.persistence_testkit import seed_qa_graph_with_db_async
from tests.rag.test_vector_store import _store


def _parse_sse_stream(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((event_name, payload))
    return events


def _paper_chunk(paper_id: str, chunk_id: str, text: str) -> PaperChunk:
    return PaperChunk(
        chunk_id=chunk_id,
        paper_id=paper_id,
        text=text,
        section="methods",
        chunk_index=0,
        source="pymupdf",
        char_start=0,
        char_end=len(text),
    )


@pytest.fixture
async def qa_e2e_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """App with graph + in-memory mock vector index wired through app.state."""
    graph_dir = tmp_path / "graphs"
    monkeypatch.setenv("QA_RETRIEVAL_TIMEOUT_SECONDS", "3")

    paper_id = "hss-001"
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
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
    await seed_qa_graph_with_db_async(tmp_path, monkeypatch, graph, graph_dir=graph_dir)

    store, _chunk_col, _entity_col, _relation_col, _embedder = _store()
    paper_service = get_paper_service()
    await paper_service.set_active_run_id(paper_id, "e2e-run")
    await store.index_chunks(
        [
            _paper_chunk(
                paper_id,
                "c1",
                "分论点通过制度路径依赖机制支撑核心论点，实验段落含 MNIST 数据集描述。",
            ),
        ],
    )

    retriever = HybridRetriever(vector_store=store)
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    app = create_app()
    app.state.hybrid_retriever = retriever
    bind_hybrid_retriever(retriever)

    llm_text = "依据原文，分论点支撑关系见[CITE:chunk:c1]。"
    monkeypatch.setattr("backend.graph.qa.get_qa_llm_client", lambda: _fake_llm(llm_text))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    reset_hybrid_retriever()
    get_paper_service.cache_clear()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_detail_question_e2e_recalls_vector_chunks_in_sse(qa_e2e_client: AsyncClient) -> None:
    """POST /qa/stream with detail question returns chunk citation events (>0)."""
    async with qa_e2e_client.stream(
        "POST",
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "分论点如何支撑核心论点？"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        body = ""
        async for chunk in response.aiter_text():
            body += chunk

    events = _parse_sse_stream(body)
    chunk_citations = [payload for name, payload in events if name == "citation" and payload.get("type") == "chunk"]
    assert len(chunk_citations) > 0, f"expected chunk citations, got events={events}"
    assert chunk_citations[0]["chunk_id"] == "c1"
    assert chunk_citations[0]["paper_id"] == "hss-001"

    event_names = [name for name, _ in events]
    assert "message" in event_names
    assert event_names[-1] == "done"
    assert event_names[0] != "warning"
