"""V1 DoD §6.5 E — 边界处理与鲁棒性联调联试（后端 HTTP + 模块）.

与 ``frontend/src/test/v1-dod-e-robustness-fe-be.integration.test.ts`` 成对验收。
覆盖：功能真实可用、边界输入、红灯路径异常码与用户可读 message。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import QaEvent, _GraphQaEngine
from backend.graph.store import GraphStore
from backend.llm.client import LlmClient, reset_llm_client_cache
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope
from tests.graph.test_qa import _bad_llm, _fake_llm
from tests.helpers.patrol_graphs import build_hss_graph_with_lens, build_hss_graph_without_lens, seed_patrol_graphs

VALID_PDF = b"%PDF-1.4\n% E robustness upload test"


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
# E-01～E-04 — Papers 图谱 / 详情 / 上传 / 失败态
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e01_graph_not_ready_when_paper_processing(api_client: AsyncClient) -> None:
    """E-01: processing 论文 GET graph → 409 GRAPH_NOT_READY + message."""
    response = await api_client.get("/api/v1/papers/hss-002/graph")
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert "就绪" in body["error"]["message"] or body["error"]["message"]


@pytest.mark.asyncio
async def test_e02_paper_not_found_returns_404_envelope(api_client: AsyncClient) -> None:
    """E-02: 不存在论文 → 404 PAPER_NOT_FOUND."""
    response = await api_client.get("/api/v1/papers/ghost-paper-404")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_e03_upload_non_pdf_returns_ingest_failed(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-03: 非 PDF / 损坏文件 → 400 INGEST_FAILED."""
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("bad.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")


@pytest.mark.asyncio
async def test_e04_failed_status_exposes_error_code_and_stage(api_client: AsyncClient) -> None:
    """E-04: failed 论文 status 含 error_code + failed_during."""
    response = await api_client.get("/api/v1/papers/hss-failed-001/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "LLM_JSON_INVALID"
    assert data["failed_during"] == "classifying"
    assert isinstance(data["message"], str) and data["message"]


# ---------------------------------------------------------------------------
# E-05～E-06 — Patrol 边界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "paper_ids",
    [
        ["hss-001"],
        ["hss-001", "hss-002", "hss-003"],
        [],
    ],
)
async def test_e05_patrol_rejects_invalid_paper_count(
    api_client: AsyncClient,
    paper_ids: list[str],
) -> None:
    """E-05: paper_ids 数量 ≠ 2 → 422 + JSON envelope（非 500）."""
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": paper_ids, "mode": "lens_clash"},
    )
    assert response.status_code == 422
    body = response.json()
    # Pydantic 校验失败为 FastAPI ``detail``；业务错误为 envelope ``error``
    assert "error" in body or "detail" in body
    if "error" in body:
        assert isinstance(body["error"].get("message"), str)
    else:
        assert isinstance(body["detail"], list) and body["detail"]


@pytest.mark.asyncio
async def test_e06_patrol_insufficient_lens_data_422_with_code(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06: 图谱缺 AnalyticalLens → 422 PATROL_INSUFFICIENT_DATA."""
    store = GraphStore(base_dir=mock_llm_env)
    store.save(build_hss_graph_without_lens("hss-001"))
    store.save(build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label="视角 B"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), code="PATROL_INSUFFICIENT_DATA")


@pytest.mark.asyncio
async def test_e06_patrol_graph_not_ready_409_with_message(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06: 未 seed 图谱 → 409 GRAPH_NOT_READY."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 409
    body = response.json()
    assert_error_envelope(body, code="GRAPH_NOT_READY")
    assert body["error"]["message"]


# ---------------------------------------------------------------------------
# E-08～E-11 — QA SSE 红路径与空图谱
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e08_qa_sse_graph_missing_error_then_done(
    api_client: AsyncClient,
    mock_llm_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-08: 图谱文件缺失 → SSE error(code+message) + done（HTTP 200 流）."""
    empty_dir = tmp_path / "graphs-missing"
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
    assert events[0][1]["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_e08_qa_sse_llm_failure_emits_qa_stream_error(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-08 / E-10: LLM 异常 → QA_STREAM_ERROR + 可读 message."""
    store = GraphStore(base_dir=mock_llm_env)
    engine = _GraphQaEngine(store=store, llm=_bad_llm())

    async def _fail_stream(paper_id: str, question: str) -> AsyncIterator[QaEvent]:
        async for evt in engine.stream(paper_id, question):
            yield evt

    monkeypatch.setattr("backend.graph.qa.qa_stream", _fail_stream)

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "会失败吗？"},
    )
    events = _parse_sse(response.text)
    error = next((payload for name, payload in events if name == "error"), None)
    assert error is not None
    assert error["code"] == "QA_STREAM_ERROR"
    assert "LLM connection refused" in error["message"]
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_e09_qa_citation_unknown_node_id_uses_node_id_as_label(
    api_client: AsyncClient,
    mock_llm_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-09: 未知 node_id citation 仍输出完整 payload，label 回退为 node_id."""
    llm_text = "引用[CITE:ghost-node]完成。"
    engine = _GraphQaEngine(store=GraphStore(base_dir=mock_llm_env), llm=_fake_llm(llm_text))

    async def _ghost_stream(paper_id: str, question: str) -> AsyncIterator[QaEvent]:
        async for evt in engine.stream(paper_id, question):
            yield evt

    monkeypatch.setattr("backend.graph.qa.qa_stream", _ghost_stream)

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "边界 citation"},
    )
    citation = next((payload for name, payload in _parse_sse(response.text) if name == "citation"), None)
    assert citation is not None
    assert citation["node_id"] == "ghost-node"
    assert citation["label"] == "ghost-node"
    assert citation["paper_id"] == "hss-001"


@pytest.mark.asyncio
async def test_e11_empty_graph_nodes_still_streams_without_sse_error(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-11: 空节点图谱不 500；仍 message + done（prompt 含友好占位）."""
    store = GraphStore(base_dir=mock_llm_env)
    store.save(
        UnifiedPaperGraph(
            paper_id="hss-001",
            paradigm=Paradigm.HSS,
            nodes=[],
            edges=[],
        ),
    )

    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "xyzzy 无匹配关键词"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert not any(name == "error" for name, _ in events)
    assert any(name == "message" for name, _ in events)
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_e11_obscure_question_still_returns_functional_mock_answer(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-11: 无关键词匹配时 fallback 子图 + Mock LLM 仍可完成问答."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "xyzzy plugh 完全无关的问题"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1][0] == "done"
    messages = "".join(payload["delta"] for name, payload in events if name == "message")
    assert messages


# ---------------------------------------------------------------------------
# E-10 — LLM 配置 / health
# ---------------------------------------------------------------------------


def test_e10_live_mode_missing_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """E-10: live 模式缺 Key → ValueError 含中文指引（非裸 500）."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with pytest.raises(ValueError, match="缺少 LLM API Key"):
        LlmClient()


@pytest.mark.asyncio
async def test_e10_health_reports_mock_mode_and_disconnected(api_client: AsyncClient, mock_llm_env: Path) -> None:
    """E-10: mock 模式下 health 明示未接云服务."""
    _ = mock_llm_env
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["llm_mode"] == "mock"
    assert data["llm_connected"] is False
    assert "尚未接入" in data["llm_note"]


# ---------------------------------------------------------------------------
# E-14 — 功能路径：Patrol 成功产出 insight
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e14_patrol_functional_returns_structured_insights(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-14: 正常双文巡检返回非空 insights + node_refs（功能可用）."""
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
    assert len(data["insights"]) >= 1
    insight = data["insights"][0]
    assert insight["title"]
    assert insight["summary"]
    assert len(insight["node_refs"]) == 2


# ---------------------------------------------------------------------------
# E-15 — 畸形请求不 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e15_patrol_malformed_json_returns_422_not_500(api_client: AsyncClient) -> None:
    """E-15: 畸形 JSON → 422，服务端不裸 500."""
    response = await api_client.post(
        "/api/v1/patrol",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_e15_qa_stream_malformed_json_returns_422_not_500(
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
