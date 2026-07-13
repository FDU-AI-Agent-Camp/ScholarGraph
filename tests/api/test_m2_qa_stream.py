"""HTTP: M2 multi-scale QA (A-09) — functional + boundary + red-path SSE feedback."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa_samples import M2_DEMO_PAPER_ID, M2_HSS_QUESTIONS, seed_m2_qa_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.llm.mock_chat import MOCK_DISCLAIMER
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_error_envelope
from tests.graph.test_qa import _bad_llm, _fake_llm
from tests.helpers.persistence_testkit import register_ready_paper, run_async, setup_qa_persistence_env


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
def m2_http_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    graph_dir = tmp_path / "graphs"
    setup_qa_persistence_env(tmp_path, monkeypatch, graph_dir=graph_dir)
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()
    seed_m2_qa_graph(graph_dir)
    run_async(register_ready_paper(M2_DEMO_PAPER_ID))
    return graph_dir


@pytest.mark.asyncio
@pytest.mark.parametrize("sample", M2_HSS_QUESTIONS, ids=lambda s: s.scale)
async def test_m2_http_mock_emits_verifiable_citation_per_scale(
    api_client: AsyncClient,
    m2_http_env,
    sample,
) -> None:
    """A-09: POST qa/stream returns graph-backed citation for summary/detail/verification."""
    _ = m2_http_env
    response = await api_client.post(
        f"/api/v1/papers/{M2_DEMO_PAPER_ID}/qa/stream",
        json={"question": sample.question},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    events = _parse_sse(response.text)
    assert not any(name == "error" for name, _ in events)
    assert events[-1][0] == "done"

    messages = "".join(payload["delta"] for name, payload in events if name == "message")
    assert MOCK_DISCLAIMER in messages

    citations = [payload for name, payload in events if name == "citation"]
    assert len(citations) >= 1
    cite = citations[0]
    assert cite["paper_id"] == M2_DEMO_PAPER_ID

    graph = GraphStore(base_dir=m2_http_env).load(M2_DEMO_PAPER_ID)
    assert graph is not None
    node = next(n for n in graph.nodes if n.id == cite["node_id"])
    assert cite["label"] == node.label
    assert node.type in sample.expected_node_types


@pytest.mark.asyncio
async def test_m2_http_graph_not_found_sse_error_feedback(
    api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_dir = tmp_path / "no-graphs"
    empty_dir.mkdir()
    setup_qa_persistence_env(tmp_path, monkeypatch, graph_dir=empty_dir)
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()
    run_async(register_ready_paper(M2_DEMO_PAPER_ID))

    response = await api_client.post(
        f"/api/v1/papers/{M2_DEMO_PAPER_ID}/qa/stream",
        json={"question": M2_HSS_QUESTIONS[0].question},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
    assert M2_DEMO_PAPER_ID in events[0][1]["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_m2_http_unknown_paper_returns_404_envelope(
    api_client: AsyncClient,
    m2_http_env,
) -> None:
    _ = m2_http_env
    response = await api_client.post(
        "/api/v1/papers/ghost-paper/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_m2_http_rejects_whitespace_only_question(
    api_client: AsyncClient,
    m2_http_env,
) -> None:
    _ = m2_http_env
    response = await api_client.post(
        f"/api/v1/papers/{M2_DEMO_PAPER_ID}/qa/stream",
        json={"question": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_m2_http_llm_failure_emits_qa_stream_error_in_sse(
    api_client: AsyncClient,
    m2_http_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.graph.qa import _GraphQaEngine
    from tests.helpers.qa_stream_mock import qa_stream_from_engine

    engine = _GraphQaEngine(store=GraphStore(base_dir=m2_http_env), llm=_bad_llm())
    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    response = await api_client.post(
        f"/api/v1/papers/{M2_DEMO_PAPER_ID}/qa/stream",
        json={"question": M2_HSS_QUESTIONS[0].question},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    error_evt = next((payload for name, payload in events if name == "error"), None)
    assert error_evt is not None
    assert error_evt["code"] == "QA_STREAM_ERROR"
    assert "LLM connection refused" in error_evt["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_m2_http_citation_survives_chunked_mock_stream(
    api_client: AsyncClient,
    m2_http_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: long node ids (n_lens) must still emit citation events over chunked SSE."""
    from backend.graph.qa import _GraphQaEngine
    from tests.helpers.qa_stream_mock import qa_stream_from_engine

    llm_text = "验证节点[CITE:n_lens]完成。"
    engine = _GraphQaEngine(
        store=GraphStore(base_dir=m2_http_env),
        llm=_fake_llm(llm_text, chunk_size=8),
    )
    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    response = await api_client.post(
        f"/api/v1/papers/{M2_DEMO_PAPER_ID}/qa/stream",
        json={"question": M2_HSS_QUESTIONS[2].question},
    )
    events = _parse_sse(response.text)
    citation = next((payload for name, payload in events if name == "citation"), None)
    assert citation is not None
    assert citation["node_id"] == "n_lens"
