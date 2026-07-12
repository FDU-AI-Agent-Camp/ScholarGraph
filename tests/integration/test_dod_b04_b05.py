"""V1 DoD B-04 / B-05 — SSE QA 真流 + citation payload 前后端联调联试.

覆盖：功能可用、边界鲁棒、红灯异常（404 JSON / SSE error+done）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.api.sse import QA_STREAM_HEADERS, format_sse_event
from backend.config import get_settings
from backend.graph.qa import _GraphQaEngine
from backend.graph.store import GraphStore
from backend.llm.mock_chat import MOCK_DISCLAIMER
from httpx import AsyncClient

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


def _assert_b05_citation(payload: dict, *, paper_id: str, graph_dir: Path) -> None:
    """B-05: citation must carry paper_id + node_id + label verifiable against graph."""
    assert set(payload.keys()) >= {"paper_id", "node_id", "label"}
    assert payload["paper_id"] == paper_id
    assert isinstance(payload["node_id"], str) and payload["node_id"]
    assert isinstance(payload["label"], str) and payload["label"]

    graph = GraphStore(base_dir=graph_dir).load(paper_id)
    assert graph is not None
    node = next((n for n in graph.nodes if n.id == payload["node_id"]), None)
    if node is not None:
        assert payload["label"] == node.label


@pytest.mark.asyncio
async def test_b04_functional_mock_stream_emits_contract_events(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """Route → qa_stream() → Mock LLM: message + citation + done (no stub)."""
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "这篇论文的核心论点是什么？"},
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
    assert not any(name == "error" for name in names)

    full_text = "".join(payload["delta"] for name, payload in events if name == "message")
    assert MOCK_DISCLAIMER in full_text

    citation = next(payload for name, payload in events if name == "citation")
    _assert_b05_citation(citation, paper_id="hss-001", graph_dir=mock_llm_env)

    done = events[-1][1]
    assert isinstance(done.get("answer_id"), str)
    assert done["answer_id"].startswith("ans-")


@pytest.mark.asyncio
async def test_b04_boundary_trims_question_before_stream(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "  \t核心论点？\n  "},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1][0] == "done"
    assert not any(name == "error" for name, _ in events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"question": ""}, 422),
        ({"question": "   "}, 422),
        ({"question": "x" * 4001}, 422),
        ({}, 422),
        ({"question": 123}, 422),
    ],
)
async def test_b04_boundary_rejects_invalid_question_payload(
    api_client: AsyncClient,
    mock_llm_env: Path,
    payload: dict,
    expected_status: int,
) -> None:
    _ = mock_llm_env
    response = await api_client.post("/api/v1/papers/hss-001/qa/stream", json=payload)
    assert response.status_code == expected_status
    assert "text/event-stream" not in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_b04_boundary_rejects_malformed_json_body(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_b04_red_unknown_paper_returns_json_404_not_sse(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """api-contract §8: errors before stream are JSON envelopes, not SSE."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/no-such-paper/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 404
    assert "application/json" in response.headers.get("content-type", "")
    assert "text/event-stream" not in response.headers.get("content-type", "")
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_b04_red_graph_missing_emits_sse_error_then_done(
    api_client: AsyncClient,
    mock_llm_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_dir = tmp_path / "graphs-empty"
    empty_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(empty_dir))
    get_settings.cache_clear()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
    assert "hss-001" in events[0][1]["message"]
    assert isinstance(events[0][1]["message"], str) and events[0][1]["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_b04_red_llm_failure_emits_qa_stream_error_in_sse(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = GraphStore(base_dir=mock_llm_env)
    engine = _GraphQaEngine(store=store, llm=_bad_llm())
    from tests.helpers.qa_stream_mock import qa_stream_from_engine

    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "会触发 LLM 失败吗？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    error = next((payload for name, payload in events if name == "error"), None)
    assert error is not None
    assert error["code"] == "QA_STREAM_ERROR"
    assert "LLM connection refused" in error["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_b05_citation_unknown_node_id_falls_back_to_node_id_label(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundary: LLM cites a node absent from graph — label falls back to node_id."""
    llm_text = "引用未知节点[CITE:ghost-node]完成。"
    engine = _GraphQaEngine(store=GraphStore(base_dir=mock_llm_env), llm=_fake_llm(llm_text))
    from tests.helpers.qa_stream_mock import qa_stream_from_engine

    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "边界测试"},
    )
    events = _parse_sse(response.text)
    citation = next((payload for name, payload in events if name == "citation"), None)
    assert citation is not None
    assert citation["paper_id"] == "hss-001"
    assert citation["node_id"] == "ghost-node"
    assert citation["label"] == "ghost-node"


@pytest.mark.asyncio
async def test_b04_sse_frames_match_format_sse_event_helper() -> None:
    """Wire format parity with backend.api.sse.format_sse_event (api-contract §8)."""
    frame = format_sse_event("message", {"delta": "片段"})
    assert frame.startswith("event: message\n")
    assert 'data: {"delta": "片段"}' in frame
    assert frame.endswith("\n\n")

    parsed = _parse_sse(frame)
    assert parsed == [("message", {"delta": "片段"})]
