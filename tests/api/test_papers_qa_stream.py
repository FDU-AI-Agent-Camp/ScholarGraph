"""HTTP: POST /api/v1/papers/{id}/qa/stream — SSE wired to qa_stream()."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import QaEvent, _GraphQaEngine
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.llm.mock_chat import MOCK_DISCLAIMER
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_error_envelope
from tests.graph.test_qa import _bad_llm, _fake_llm


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
async def api_client() -> AsyncIterator[AsyncClient]:
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


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

    async def _fake_qa_stream(paper_id: str, question: str) -> AsyncIterator[QaEvent]:
        async for evt in engine.stream(paper_id, question):
            yield evt

    monkeypatch.setattr("backend.graph.qa.qa_stream", _fake_qa_stream)

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

    async def _fail_stream(paper_id: str, question: str) -> AsyncIterator[QaEvent]:
        async for evt in engine.stream(paper_id, question):
            yield evt

    monkeypatch.setattr("backend.graph.qa.qa_stream", _fail_stream)

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    error_evt = next((payload for name, payload in events if name == "error"), None)
    assert error_evt is not None
    assert error_evt["code"] == "QA_STREAM_ERROR"
