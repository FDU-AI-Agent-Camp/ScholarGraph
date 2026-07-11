"""B-04 — POST /papers/{id}/qa/stream wired to qa_stream() with frozen SSE contract."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.api.sse import QA_STREAM_HEADERS, format_sse_event
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.llm.mock_chat import MOCK_DISCLAIMER
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_error_envelope

_SSE_FRAME_RE = re.compile(
    r"^event: (?P<event>\w+)\ndata: (?P<data>\{.*\})\n\n$",
    re.MULTILINE,
)


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
def b04_qa_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from backend.graph.qa_samples import seed_m2_qa_graph

    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_llm_client_cache()
    seed_m2_qa_graph(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _hybrid_retriever_without_vector_store() -> AsyncIterator[None]:
    """Avoid ChromaDB init on B-04 HTTP QA tests; vectors are opt-in per test."""
    from backend.main import app
    from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever

    retriever = HybridRetriever(vector_store=None)
    app.state.hybrid_retriever = retriever
    bind_hybrid_retriever(retriever)
    yield
    reset_hybrid_retriever()
    if hasattr(app.state, "hybrid_retriever"):
        delattr(app.state, "hybrid_retriever")


def test_format_sse_event_matches_api_contract_section_8() -> None:
    frame = format_sse_event("citation", {"paper_id": "hss-001", "node_id": "n1", "label": "核心论点"})
    match = _SSE_FRAME_RE.search(frame)
    assert match is not None
    assert match.group("event") == "citation"
    payload = json.loads(match.group("data"))
    assert payload == {"paper_id": "hss-001", "node_id": "n1", "label": "核心论点"}


@pytest.mark.asyncio
async def test_b04_route_streams_real_qa_without_monkeypatch(
    api_client: AsyncClient,
    b04_qa_env: Path,
) -> None:
    """Route → qa_stream() → SSE (no route-level stub)."""
    _ = b04_qa_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "这篇论文做了什么？"},
        headers={"Accept": "text/event-stream"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert response.headers.get("cache-control") == QA_STREAM_HEADERS["Cache-Control"]
    assert response.headers.get("x-accel-buffering") == QA_STREAM_HEADERS["X-Accel-Buffering"]

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert "message" in names
    assert "citation" in names
    assert names[-1] == "done"

    messages = "".join(payload["delta"] for name, payload in events if name == "message")
    assert MOCK_DISCLAIMER in messages

    citation = next(payload for name, payload in events if name == "citation")
    assert citation.keys() >= {"paper_id", "node_id", "label"}
    assert citation["paper_id"] == "hss-001"
    graph = GraphStore(base_dir=b04_qa_env).load("hss-001")
    assert graph is not None
    node = next(n for n in graph.nodes if n.id == citation["node_id"])
    assert citation["label"] == node.label


@pytest.mark.asyncio
async def test_b04_unknown_paper_returns_json_404_before_sse(
    api_client: AsyncClient,
    b04_qa_env: Path,
) -> None:
    _ = b04_qa_env
    response = await api_client.post(
        "/api/v1/papers/no-such-paper/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 404
    assert "text/event-stream" not in response.headers.get("content-type", "")
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_b04_graph_missing_emits_error_then_done_in_sse(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = tmp_path / "empty-graphs"
    empty.mkdir()
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GRAPH_DATA_DIR", str(empty))
    get_settings.cache_clear()
    reset_llm_client_cache()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
    assert isinstance(events[0][1]["message"], str)
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_b04_rejects_whitespace_question_with_422(
    api_client: AsyncClient,
    b04_qa_env: Path,
) -> None:
    _ = b04_qa_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "   \t  "},
    )
    assert response.status_code == 422
