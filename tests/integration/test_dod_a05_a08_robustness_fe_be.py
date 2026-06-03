"""V1 DoD A-05～A-08 — 绿路径 / 边界 / 红灯鲁棒性（BE 侧，与 FE 成对）.

与 ``frontend/src/test/v1-dod-a05-a08-robustness-fe-be.integration.test.ts`` 成对。
"""

from __future__ import annotations

import json

import pytest
from backend.agents.classifier import classify
from backend.agents.extractor import extract
from backend.graph.store import GraphStore
from backend.schemas.paradigm import Paradigm
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope
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


# ---------------------------------------------------------------------------
# A-05 — QA SSE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a05_green_padded_question_accepted_after_strip(api_client: AsyncClient, mock_llm_env) -> None:
    """边界：首尾空白 strip 后仍应 200 且产出 citation。"""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "  核心论点是什么？  "},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert any(name == "citation" for name, _ in events)
    assert events[-1][0] == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "   \t\n  "},
    ],
)
async def test_a05_boundary_empty_question_returns_422(
    api_client: AsyncClient,
    mock_llm_env,
    payload: dict[str, str],
) -> None:
    _ = mock_llm_env
    response = await api_client.post("/api/v1/papers/hss-001/qa/stream", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a05_boundary_missing_question_field_422(api_client: AsyncClient, mock_llm_env) -> None:
    _ = mock_llm_env
    response = await api_client.post("/api/v1/papers/hss-001/qa/stream", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a05_red_processing_paper_without_graph_emits_graph_not_found_sse(
    api_client: AsyncClient,
    mock_llm_env,
) -> None:
    """hss-002 在种子中为 processing；无图谱文件时应 SSE error + done（非 500）。"""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-002/qa/stream",
        json={"question": "这篇论文在讲什么？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
    assert "图谱" in events[0][1]["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_a05_red_graph_not_found_message_is_user_facing(
    api_client: AsyncClient,
    mock_llm_env,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_dir = tmp_path / "no-graphs"
    empty_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(empty_dir))
    from backend.config import get_settings

    get_settings.cache_clear()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 200
    error = _parse_sse(response.text)[0][1]
    assert error["code"] == "GRAPH_NOT_FOUND"
    assert len(error["message"]) >= 8
    assert "hss-001" in error["message"]


@pytest.mark.asyncio
async def test_a05_red_unknown_paper_404_envelope_has_message(api_client: AsyncClient, mock_llm_env) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/no-such-paper/qa/stream",
        json={"question": "test"},
    )
    assert response.status_code == 404
    body = response.json()
    assert_error_envelope(body, code="PAPER_NOT_FOUND")
    assert "no-such-paper" in body["error"]["message"] or body["error"]["message"]


# ---------------------------------------------------------------------------
# A-06 — Patrol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "paper_ids",
    [
        ["hss-001"],
        ["hss-001", "hss-002", "hss-003"],
    ],
)
async def test_a06_boundary_invalid_paper_count_422(
    api_client: AsyncClient,
    mock_llm_env,
    paper_ids: list[str],
) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": paper_ids, "mode": "lens_clash"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a06_green_contradiction_mode_returns_thesis_insight(api_client: AsyncClient, mock_llm_env) -> None:
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis

    store = GraphStore(base_dir=mock_llm_env)
    store.save(build_hss_graph_with_thesis("hss-001", thesis_id="n_a", thesis_label="论点 A"))
    store.save(build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="论点 B"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "contradiction"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "contradiction"
    insight = data["insights"][0]
    assert len(insight["node_refs"]) == 2
    ref = insight["node_refs"][0]
    assert ref["paper_id"] and ref["node_id"] and ref["label"]


@pytest.mark.asyncio
async def test_a06_green_lens_clash_node_refs_navigable_shape(api_client: AsyncClient, mock_llm_env) -> None:
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
    for ref in response.json()["data"]["insights"][0]["node_refs"]:
        assert ref["paper_id"] in {"hss-001", "hss-002"}
        assert ref["node_id"]
        assert ref["label"]


@pytest.mark.asyncio
async def test_a06_red_graph_not_ready_409_message_non_empty(api_client: AsyncClient, mock_llm_env) -> None:
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert "未就绪" in body["error"]["message"] or "图谱" in body["error"]["message"]


@pytest.mark.asyncio
async def test_a06_red_insufficient_data_422_message_non_empty(api_client: AsyncClient, mock_llm_env) -> None:
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
    assert body["error"]["message"]


# ---------------------------------------------------------------------------
# A-07 / A-08 — Agent 输入契约
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a07_red_classify_empty_input_raises(live_llm_env) -> None:
    _ = live_llm_env
    with pytest.raises(ValueError, match="non-empty"):
        await classify("")


@pytest.mark.asyncio
async def test_a07_red_classify_whitespace_only_raises(live_llm_env) -> None:
    _ = live_llm_env
    with pytest.raises(ValueError, match="non-empty"):
        await classify("   \n\t  ")


@pytest.mark.asyncio
async def test_a08_red_extract_empty_input_raises(live_llm_env) -> None:
    _ = live_llm_env
    with pytest.raises(ValueError, match="non-empty"):
        await extract("", Paradigm.HSS)


@pytest.fixture
def live_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    from backend.config import get_settings
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()
