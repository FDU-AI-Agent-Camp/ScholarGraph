"""Week 4 B/C merge gate — STEM QA SSE symmetry when vector store is unavailable."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa_samples import STEM_DEMO_PAPER_ID, seed_stem_qa_graph
from backend.llm.client import reset_llm_client_cache
from backend.main import app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service
from backend.services.qa_retrieval import (
    VECTOR_RETRIEVAL_WARNING_SOURCE,
    VECTOR_STORE_UNAVAILABLE_CODE,
    VECTOR_STORE_UNAVAILABLE_MESSAGE,
)
from httpx import ASGITransport, AsyncClient

from tests.graph.test_qa import _fake_llm
from tests.helpers.b10_qa_boundary import parse_sse_body
from tests.helpers.vector_store_doubles import ExistsFaultVectorStore

STEM_DETAIL_QUESTION = "ResNet-Light 在 ImageNet 上的 top-1 accuracy 是多少？"


@pytest.fixture
def stem_qa_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    reset_hybrid_retriever()
    reset_llm_client_cache()
    seed_stem_qa_graph(graph_dir, paper_id=STEM_DEMO_PAPER_ID)
    return STEM_DEMO_PAPER_ID, graph_dir


@pytest.fixture
async def stem_outage_http_client(
    stem_qa_env: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    paper_id, _graph_dir = stem_qa_env
    fault_store = ExistsFaultVectorStore()
    retriever = HybridRetriever(vector_store=fault_store)
    bind_hybrid_retriever(retriever)

    paper_service = get_paper_service()
    paper = await paper_service.get_paper(paper_id)
    assert paper.status == PaperStatus.READY

    llm_text = "根据图谱，ResNet-Light 达到[CITE:n_claim]。"
    monkeypatch.setattr("backend.graph.qa.get_qa_llm_client", lambda: _fake_llm(llm_text, chunk_size=4))
    reset_llm_client_cache()

    app.state.hybrid_retriever = retriever

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    reset_hybrid_retriever()


@pytest.mark.asyncio
async def test_stem_qa_sse_emits_vector_store_warning_before_message(
    stem_outage_http_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """主动断网演练：向量库不可用时 SSE warning 与 timeout 对称，图谱兜底完成问答。"""
    caplog.set_level(logging.WARNING, logger="backend.services.qa_retrieval")

    response = await stem_outage_http_client.post(
        f"/api/v1/papers/{STEM_DEMO_PAPER_ID}/qa/stream",
        json={"question": STEM_DETAIL_QUESTION},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    outage_logs = [
        record
        for record in caplog.records
        if "qa_retrieval_vector_store_unavailable" in record.getMessage()
    ]
    assert len(outage_logs) == 1
    assert outage_logs[0].exc_info is not None
    assert "ConnectionError" in caplog.text
    assert "connection refused" in caplog.text

    events = parse_sse_body(response.text)
    event_names = [name for name, _ in events]
    assert event_names[0] == "warning"
    warning = events[0][1]
    assert warning["code"] == VECTOR_STORE_UNAVAILABLE_CODE
    assert warning["message"] == VECTOR_STORE_UNAVAILABLE_MESSAGE
    assert warning["source"] == VECTOR_RETRIEVAL_WARNING_SOURCE

    message_index = event_names.index("message")
    assert message_index > 0
    assert "error" not in event_names
    assert event_names[-1] == "done"

    full_text = "".join(payload["delta"] for name, payload in events if name == "message")
    assert full_text.strip()
