"""HTTP: POST /api/v1/papers/{id}/qa/stream — SSE wired to qa_stream()."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from backend.config import get_settings
from backend.graph.qa import QaEvent, _GraphQaEngine
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.llm.mock_chat import MOCK_DISCLAIMER
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope
from tests.graph.test_qa import _bad_llm, _fake_llm
from tests.helpers.qa_stream_mock import qa_stream_from_engine


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((event_name, payload))
    return events


@pytest.fixture
def qa_graph_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    from backend.config import get_settings

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


@pytest.mark.asyncio
async def test_qa_stream_http_emits_message_citation_done(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_text = "核心论点[CITE:n1]涉及不平等。"
    engine = _GraphQaEngine(store=qa_graph_store, llm=_fake_llm(llm_text))
    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点是什么？"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    events = _parse_sse(response.text)
    event_names = [name for name, _ in events]
    assert "message" in event_names
    assert "citation" in event_names
    assert event_names[-1] == "done"

    citation = next(payload for name, payload in events if name == "citation")
    assert citation["paper_id"] == "hss-001"
    assert citation["node_id"] == "n1"
    assert "核心论点" in citation["label"]


@pytest.mark.asyncio
async def test_qa_stream_http_missing_graph_emits_error_then_done(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path / "empty-graphs"))
    from backend.config import get_settings

    get_settings.cache_clear()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_qa_stream_http_rejects_empty_question(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_qa_stream_http_unknown_paper_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/papers/does-not-exist/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_qa_stream_http_mock_mode_without_monkeypatch(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM_MODE=mock: real qa_stream path emits mock disclaimer + citation."""
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点是什么？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    full_text = "".join(payload["delta"] for name, payload in events if name == "message")
    assert MOCK_DISCLAIMER in full_text
    assert any(name == "citation" for name, _ in events)


@pytest.mark.asyncio
async def test_qa_stream_http_rejects_missing_question_field(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/papers/hss-001/qa/stream", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_qa_stream_http_rejects_question_over_4000_chars(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
) -> None:
    _ = qa_graph_store
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "问" * 4001},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_qa_stream_http_llm_error_event_in_sse(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _GraphQaEngine(store=qa_graph_store, llm=_bad_llm())
    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    error_evt = next((payload for name, payload in events if name == "error"), None)
    assert error_evt is not None
    assert error_evt["code"] == "QA_STREAM_ERROR"


@pytest.mark.asyncio
async def test_qa_stream_http_wires_hybrid_retrieval_context(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP path: HybridRetriever.retrieve → qa_stream(retrieval_context=...)."""
    from backend.rag.models import QuestionScale, RetrievalContext, RetrievedChunk

    chunk = RetrievedChunk(
        id="chunk:hss-001:c1",
        paper_id="hss-001",
        text="实验在 MNIST 上达到 95% 准确率。",
        chunk_id="c1",
        chunk_index=0,
        char_start=0,
        char_end=20,
        page_start=5,
    )
    rc = RetrievalContext(scale=QuestionScale.DETAIL, chunks=[chunk])
    hybrid_retriever = AsyncMock()
    hybrid_retriever.retrieve = AsyncMock(return_value=rc)

    captured: list[RetrievalContext | None] = []
    llm_text = "参见原文[CITE:chunk:c1]。"
    engine = _GraphQaEngine(store=qa_graph_store, llm=_fake_llm(llm_text))

    async def _recording_qa_stream(
        paper_id: str,
        question: str,
        *,
        retrieval_context=None,
        retrieval_warning=None,
        llm=None,
    ) -> AsyncIterator[QaEvent]:
        captured.append(retrieval_context)
        async for evt in engine.stream(
            paper_id,
            question,
            retrieval_context=retrieval_context,
            retrieval_warning=retrieval_warning,
        ):
            yield evt

    monkeypatch.setattr("backend.graph.qa.qa_stream", _recording_qa_stream)
    bind_hybrid_retriever(hybrid_retriever)
    from backend.main import app

    app.state.hybrid_retriever = hybrid_retriever

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "分论点如何支撑核心论点？"},
    )
    assert response.status_code == 200
    assert captured and captured[0] is rc
    hybrid_retriever.retrieve.assert_awaited_once()
    assert hybrid_retriever.retrieve.await_args.kwargs["scale"] == QuestionScale.DETAIL

    events = _parse_sse(response.text)
    assert any(name == "citation" for name, _ in events)


@pytest.mark.asyncio
async def test_qa_stream_http_emits_warning_on_retrieval_timeout(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slow vector retrieval must not block SSE; emit warning and graph-only fallback."""
    from backend.services.qa_retrieval import (
        VECTOR_RETRIEVAL_TIMEOUT_CODE,
        VECTOR_RETRIEVAL_TIMEOUT_MESSAGE,
        VECTOR_RETRIEVAL_WARNING_SOURCE,
    )

    async def slow_retrieve(*args, **kwargs):
        import asyncio

        await asyncio.sleep(0.05)
        from backend.rag.models import QuestionScale, RetrievalContext

        return RetrievalContext(scale=QuestionScale.DETAIL)

    hybrid_retriever = HybridRetriever(vector_store=None)
    hybrid_retriever.retrieve = slow_retrieve  # type: ignore[method-assign]
    bind_hybrid_retriever(hybrid_retriever)
    from backend.main import app

    app.state.hybrid_retriever = hybrid_retriever
    monkeypatch.setenv("QA_RETRIEVAL_TIMEOUT_SECONDS", "0.01")
    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "分论点如何支撑核心论点？"},
    )
    assert response.status_code == 200

    events = _parse_sse(response.text)
    event_names = [name for name, _ in events]
    assert event_names[0] == "warning"
    warning = events[0][1]
    assert warning["code"] == VECTOR_RETRIEVAL_TIMEOUT_CODE
    assert warning["message"] == VECTOR_RETRIEVAL_TIMEOUT_MESSAGE
    assert warning["source"] == VECTOR_RETRIEVAL_WARNING_SOURCE
    assert "message" in event_names
    assert event_names[-1] == "done"


@pytest.mark.asyncio
async def test_qa_stream_http_blank_paper_without_vector_index_completes(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph-only fallback when vector index is missing: SSE completes without error."""
    _ = qa_graph_store
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "分论点如何支撑核心论点？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    event_names = [name for name, _ in events]
    assert "error" not in event_names
    assert "message" in event_names
    assert event_names[-1] == "done"


@pytest.mark.asyncio
async def test_qa_stream_http_rejects_cross_paper_question_with_400(
    api_client: AsyncClient,
    qa_graph_store: GraphStore,
) -> None:
    """Cross-paper intent must return 400 and guide users to Patrol."""
    _ = qa_graph_store
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "How does this model compare to ResNet50?"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == ("当前问答接口仅支持单篇论文深度解析。若要对比多篇论文，请前往 /patrol 跨论文巡航模块。")
