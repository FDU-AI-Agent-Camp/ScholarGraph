"""V1 DoD §6.5 E-06～E-10 — 边界鲁棒性前后端联调联试（BE 侧）.

与 ``frontend/src/test/v1-dod-e06-e10-fe-be.integration.test.ts`` 成对。
含 E-01～E-05 回归冒烟，确保巡检 / QA SSE / LLM 路径与文献主路径一致。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import get_settings
from backend.graph.qa import QaEvent, _GraphQaEngine
from backend.graph.store import GraphStore
from backend.llm.client import LlmClient, reset_llm_client_cache
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.graph.test_qa import _bad_llm, _fake_llm
from tests.helpers.patrol_graphs import (
    build_hss_graph_with_lens,
    build_hss_graph_with_thesis,
    build_hss_graph_without_lens,
    build_hss_graph_without_thesis,
    seed_patrol_graphs,
)

READY_ID = "hss-001"
PROCESSING_ID = "hss-002"


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
# E-06 — Patrol 图谱缺失 / 节点不足
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e06_patrol_graph_not_ready_409_with_readable_message(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06 红灯：未 seed 图谱 → 409 GRAPH_NOT_READY + message（非 500）."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": [READY_ID, PROCESSING_ID], "mode": "lens_clash"},
    )
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert body["error"]["message"]


@pytest.mark.asyncio
async def test_e06_patrol_insufficient_lens_422_patrol_insufficient_data(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06 红灯：缺 AnalyticalLens → 422 PATROL_INSUFFICIENT_DATA."""
    store = GraphStore(base_dir=mock_llm_env)
    store.save(build_hss_graph_without_lens(READY_ID))
    store.save(build_hss_graph_with_lens(PROCESSING_ID, lens_id="n_lens_b", lens_label="视角 B"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": [READY_ID, PROCESSING_ID], "mode": "lens_clash"},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), code="PATROL_INSUFFICIENT_DATA")


@pytest.mark.asyncio
async def test_e06_patrol_contradiction_insufficient_data_returns_200(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06 绿灯：contradiction 缺 Thesis → 200 + status=insufficient_data."""
    store = GraphStore(base_dir=mock_llm_env)
    store.save(build_hss_graph_without_thesis(READY_ID))
    store.save(
        build_hss_graph_with_thesis(
            PROCESSING_ID,
            thesis_id="n_thesis_b",
            thesis_label="论点 B",
        ),
    )

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": [READY_ID, PROCESSING_ID], "mode": "contradiction"},
    )
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    insight = body["data"]["insights"][0]
    assert insight["insight_id"] == "ins-contradiction-001"
    assert insight["status"] == "insufficient_data"
    assert insight["has_contradiction"] is False


@pytest.mark.asyncio
async def test_e06_green_patrol_lens_clash_functional_when_graphs_ready(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06 功能对照：双文图谱完备时巡检 200."""
    seed_patrol_graphs(
        mock_llm_env,
        {
            READY_ID: ("n_lens_a", "消费社会"),
            PROCESSING_ID: ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": [READY_ID, PROCESSING_ID], "mode": "lens_clash"},
    )
    assert response.status_code == 200
    assert_success_envelope(response.json())


# ---------------------------------------------------------------------------
# E-07 / E-08 — QA SSE 连接与 error 事件
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e07_e08_sse_error_event_always_ends_with_done(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-08：SSE error 后仍发 done；HTTP 200 流（E-07 由 FE onerror 处理断连）."""
    store = GraphStore(base_dir=mock_llm_env)
    engine = _GraphQaEngine(store=store, llm=_bad_llm())
    from tests.helpers.qa_stream_mock import qa_stream_from_engine

    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "触发 LLM 失败"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    error = next((payload for name, payload in events if name == "error"), None)
    assert error is not None
    assert error["code"] == "QA_STREAM_ERROR"
    assert error["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_e08_sse_graph_not_found_error_payload_for_fe_prefix(
    api_client: AsyncClient,
    mock_llm_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-08：图谱缺失 → error code GRAPH_NOT_FOUND + message（FE 展示为 错误: …）."""
    empty_dir = tmp_path / "graphs-e08"
    empty_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(empty_dir))
    get_settings.cache_clear()

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "测试"},
    )
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
    assert events[0][1]["message"]


@pytest.mark.asyncio
async def test_e07_green_qa_sse_streams_message_and_done(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-07 功能：正常 mock QA 流含 message + done."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点？"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert any(name == "message" for name, _ in events)
    assert events[-1][0] == "done"


# ---------------------------------------------------------------------------
# E-09 — citation 边界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e09_duplicate_citation_frames_emitted_from_stream(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-09：后端可连续发相同 citation；由 FE appendUniqueCitation 去重."""
    cite = {"paper_id": READY_ID, "node_id": "n1", "label": "核心论点"}
    engine = _GraphQaEngine(store=GraphStore(base_dir=mock_llm_env), llm=_fake_llm("见[CITE:n1]"))

    async def _dup_stream(
        paper_id: str,
        question: str,
        *,
        retrieval_context=None,
        llm=None,
    ) -> AsyncIterator[QaEvent]:
        async for evt in engine.stream(paper_id, question, retrieval_context=retrieval_context):
            yield evt
        yield QaEvent("citation", cite)
        yield QaEvent("citation", cite)

    monkeypatch.setattr("backend.graph.qa.qa_stream", _dup_stream)

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "重复 citation"},
    )
    citations = [payload for name, payload in _parse_sse(response.text) if name == "citation"]
    assert len(citations) >= 2
    assert all(c["node_id"] == "n1" for c in citations)


@pytest.mark.asyncio
async def test_e09_empty_node_id_citation_still_valid_payload(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-09 红灯：空 node_id 仍输出 citation 字段（FE 不崩溃）."""
    engine = _GraphQaEngine(store=GraphStore(base_dir=mock_llm_env), llm=_fake_llm("x"))

    async def _empty_cite_stream(
        paper_id: str,
        question: str,
        *,
        retrieval_context=None,
        llm=None,
    ) -> AsyncIterator[QaEvent]:
        async for evt in engine.stream(paper_id, question, retrieval_context=retrieval_context):
            yield evt
        yield QaEvent("citation", {"paper_id": READY_ID, "node_id": "", "label": ""})

    monkeypatch.setattr("backend.graph.qa.qa_stream", _empty_cite_stream)

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "空 citation"},
    )
    cite = next((p for name, p in _parse_sse(response.text) if name == "citation"), None)
    assert cite is not None
    assert cite["node_id"] == ""


# ---------------------------------------------------------------------------
# E-10 — LLM Key / 超时 / template fallback
# ---------------------------------------------------------------------------


def test_e10_live_mode_missing_key_raises_clear_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """E-10 红灯：live 缺 Key → ValueError 中文指引."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with pytest.raises(ValueError, match="缺少 LLM API Key"):
        LlmClient()


@pytest.mark.asyncio
async def test_e10_patrol_llm_summary_failure_uses_template_not_500(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-10：Patrol LLM 失败 → 200 + 模板摘要（非 500）."""
    seed_patrol_graphs(
        mock_llm_env,
        {
            READY_ID: ("n_lens_a", "消费社会"),
            PROCESSING_ID: ("n_lens_b", "公共领域"),
        },
    )
    with patch(
        "backend.patrol.lens_clash.generate_patrol_summary",
        new=AsyncMock(return_value=None),
    ):
        response = await api_client.post(
            "/api/v1/patrol",
            json={"paper_ids": [READY_ID, PROCESSING_ID], "mode": "lens_clash"},
        )

    assert response.status_code == 200
    summary = response.json()["data"]["insights"][0]["summary"]
    assert "分析视角" in summary or "消费社会" in summary


# ---------------------------------------------------------------------------
# E-01～E-05 — 回归冒烟（与专用 e01-e05 联调文件一致）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e01_regression_processing_graph_409_graph_not_ready(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{PROCESSING_ID}/graph")
    assert response.status_code == 409
    assert_error_envelope(response.json(), code="GRAPH_NOT_READY")


@pytest.mark.asyncio
async def test_e02_regression_paper_not_found_404(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/ghost-e06-e10/graph")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_e04_regression_failed_status_fields(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/hss-failed-001/status")
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"]
    assert data["failed_during"]


@pytest.mark.asyncio
async def test_e05_regression_patrol_single_paper_422(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": [READY_ID], "mode": "lens_clash"},
    )
    assert response.status_code == 422
