"""V1 DoD A-05～A-08 — cross-stack integration (mock LLM + red-path envelopes)."""

from __future__ import annotations

import json

import pytest
from backend.agents.classifier import classify
from backend.agents.extractor import extract
from backend.graph.store import GraphStore
from backend.llm.mock_chat import MOCK_DISCLAIMER, MOCK_PATROL_PREFIX
from backend.schemas.paradigm import Paradigm
from backend.services.agent_service import AgentService
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope
from tests.graph.test_qa import _bad_llm
from tests.helpers.classifier_labels import load_classifier_labels
from tests.helpers.patrol_graphs import seed_patrol_graphs


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


@pytest.mark.asyncio
async def test_a05_qa_sse_mock_mode_end_to_end(api_client: AsyncClient, mock_llm_env) -> None:
    """HTTP → qa_stream → MockChat: message + citation + done (no cloud)."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点是什么？"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert "message" in names
    assert "citation" in names
    assert names[-1] == "done"

    full_text = "".join(payload["delta"] for name, payload in events if name == "message")
    assert MOCK_DISCLAIMER in full_text
    citation = next(payload for name, payload in events if name == "citation")
    assert citation["paper_id"] == "hss-001"
    assert citation["node_id"] == "n1"


@pytest.mark.asyncio
async def test_a05_qa_sse_graph_missing_emits_graph_not_found(
    api_client: AsyncClient,
    mock_llm_env,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paper exists (fixture seed) but graph file absent → SSE error + done."""
    empty_dir = tmp_path / "empty-graphs"
    empty_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(empty_dir))
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
    assert isinstance(events[0][1]["message"], str)
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_a05_qa_sse_unknown_paper_returns_404(api_client: AsyncClient, mock_llm_env) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/ghost-paper/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_a05_qa_sse_rejects_empty_and_oversized_question(
    api_client: AsyncClient,
    mock_llm_env,
) -> None:
    _ = mock_llm_env
    empty = await api_client.post("/api/v1/papers/hss-001/qa/stream", json={"question": ""})
    assert empty.status_code == 422

    too_long = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "x" * 4001},
    )
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_a05_qa_sse_llm_failure_emits_error_event(
    api_client: AsyncClient,
    mock_llm_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulated live LLM outage → QA_STREAM_ERROR inside SSE (still 200 stream)."""
    from backend.graph.qa import _GraphQaEngine

    _ = mock_llm_env
    store = GraphStore(base_dir=mock_llm_env)
    engine = _GraphQaEngine(store=store, llm=_bad_llm())

    async def _failing_stream(paper_id: str, question: str):
        async for evt in engine.stream(paper_id, question):
            yield evt

    monkeypatch.setattr("backend.graph.qa.qa_stream", _failing_stream)

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "会失败吗？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    error = next((payload for name, payload in events if name == "error"), None)
    assert error is not None
    assert error["code"] == "QA_STREAM_ERROR"
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_a06_patrol_mock_llm_summary_in_report(api_client: AsyncClient, mock_llm_env) -> None:
    """Patrol with LLM_MODE=mock returns structured insight (mock summary or template)."""
    seed_patrol_graphs(
        mock_llm_env,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "lens_clash"
    assert len(data["insights"]) == 1
    insight = data["insights"][0]
    assert len(insight["node_refs"]) == 2
    summary = insight["summary"]
    assert MOCK_PATROL_PREFIX in summary or "分析视角" in summary


@pytest.mark.asyncio
async def test_a06_patrol_graph_not_ready_409_envelope(api_client: AsyncClient, mock_llm_env) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert body["error"]["message"]


@pytest.mark.asyncio
async def test_a06_patrol_insufficient_data_422_envelope(
    api_client: AsyncClient,
    mock_llm_env,
) -> None:
    from tests.helpers.patrol_graphs import build_hss_graph_with_lens, build_hss_graph_without_lens

    store = GraphStore(base_dir=mock_llm_env)
    store.save(build_hss_graph_without_lens("hss-001"))
    store.save(build_hss_graph_with_lens("hss-002", lens_id="n_b", lens_label="B"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 422
    body = response.json()
    assert_error_envelope(body, code="PATROL_INSUFFICIENT_DATA")


@pytest.fixture
def live_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force live LLM path so BE-2 NotImplemented tests stay valid under default mock."""
    monkeypatch.setenv("LLM_MODE", "live")
    from backend.config import get_settings
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_a07_classify_live_heuristic_returns_stem(live_llm_env) -> None:
    """BE-2 live path: heuristic classify without cloud LLM."""
    _ = live_llm_env
    result = await AgentService().classify_paradigm(
        "Title: benchmark. We evaluate the model on datasets with accuracy and baselines."
    )
    assert result.paradigm == Paradigm.STEM
    assert result.reason


@pytest.mark.asyncio
async def test_a07_classify_direct_live_heuristic(live_llm_env) -> None:
    _ = live_llm_env
    result = await classify("标题：平台零工经济。本文通过访谈材料和理论视角分析劳动者经验。")
    assert result.paradigm == Paradigm.HSS


def test_a07_gold_labels_three_papers_two_paradigms() -> None:
    rows = load_classifier_labels()
    assert {row["paper_id"] for row in rows} == {"stem-001", "hss-001", "hss-002"}


@pytest.mark.asyncio
async def test_a08_extract_live_heuristic_returns_valid_graph(live_llm_env) -> None:
    _ = live_llm_env
    graph = await AgentService().extract_graph(
        "标题：实验方法\nWe report benchmark accuracy on datasets.",
        Paradigm.STEM,
        paper_id="hss-001",
    )
    assert graph.paper_id == "hss-001"
    assert graph.paradigm == Paradigm.STEM
    assert graph.nodes


@pytest.mark.asyncio
async def test_a08_extract_direct_live_heuristic(live_llm_env) -> None:
    _ = live_llm_env
    graph = await extract(
        "标题：近代口岸研究\n本文认为通商口岸体现制度路径依赖。",
        Paradigm.HSS,
    )
    assert graph.paradigm == Paradigm.HSS
    assert any(str(node.type) == "Thesis" for node in graph.nodes)


@pytest.mark.asyncio
async def test_health_reports_mock_llm_mode(api_client: AsyncClient, mock_llm_env) -> None:
    _ = mock_llm_env
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["llm_mode"] == "mock"
    assert data["llm_connected"] is False
    assert "尚未接入" in data["llm_note"]
