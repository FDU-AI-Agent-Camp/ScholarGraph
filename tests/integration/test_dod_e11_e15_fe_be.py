"""V1 DoD §6.5 E-11～E-15 — 边界鲁棒性前后端联调联试（BE 侧）.

与 ``frontend/src/test/v1-dod-e11-e15-fe-be.integration.test.ts`` 成对。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from backend.graph.qa import _GraphQaEngine
from backend.graph.store import GraphStore
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.conftest import REPO_ROOT
from tests.graph.test_qa import _fake_llm
from tests.helpers.patrol_graphs import seed_patrol_graphs

RUN_QA_SCRIPT = REPO_ROOT / "scripts" / "run_qa.py"
RUN_PATROL_SCRIPT = REPO_ROOT / "scripts" / "run_patrol.py"
READY_ID = "hss-001"


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
# E-11 — 空图谱 / 无匹配子图
# ---------------------------------------------------------------------------


def test_e11_build_prompt_empty_subgraph_uses_friendly_placeholders(mock_llm_env: Path) -> None:
    """E-11: 无匹配子图时 prompt 含友好占位（非裸空串）."""
    engine = _GraphQaEngine(store=GraphStore(base_dir=mock_llm_env), llm=_fake_llm("x"))
    graph = UnifiedPaperGraph(
        paper_id=READY_ID,
        paradigm=Paradigm.HSS,
        nodes=[],
        edges=[],
    )
    prompt = engine._build_prompt(graph, {"nodes": [], "edges": []}, "xyzzy 无关问题")
    assert "图谱中暂无匹配节点" in prompt
    assert "无匹配关系" in prompt


@pytest.mark.asyncio
async def test_e11_empty_graph_nodes_streams_message_and_done_without_sse_error(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-11: 空节点图谱 → HTTP 200；无 SSE error；仍有 message + done."""
    store = GraphStore(base_dir=mock_llm_env)
    store.save(
        UnifiedPaperGraph(
            paper_id=READY_ID,
            paradigm=Paradigm.HSS,
            nodes=[],
            edges=[],
        ),
    )

    response = await api_client.post(
        f"/api/v1/papers/{READY_ID}/qa/stream",
        json={"question": "xyzzy 无匹配关键词"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert not any(name == "error" for name, _ in events)
    assert any(name == "message" for name, _ in events)
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_e11_obscure_question_mock_qa_still_functional(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-11 功能：无关键词匹配时 fallback 子图 + Mock LLM 仍可完成问答."""
    _ = mock_llm_env
    response = await api_client.post(
        f"/api/v1/papers/{READY_ID}/qa/stream",
        json={"question": "xyzzy plugh 完全无关的问题"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    messages = "".join(payload["delta"] for name, payload in events if name == "message")
    assert messages
    assert events[-1][0] == "done"


# ---------------------------------------------------------------------------
# E-12 — Windows 控制台 UTF-8 / ASCII CLI 输出
# ---------------------------------------------------------------------------


def test_e12_run_qa_script_uses_ascii_cli_markers_not_emoji() -> None:
    """E-12: run_qa.py CLI 使用 [OK]/[ERROR] 等 ASCII 标记（无 emoji 装饰）."""
    source = RUN_QA_SCRIPT.read_text(encoding="utf-8")
    for marker in ("[OK]", "[ERROR]", "[FAIL]", "[FATAL]", "paper_id :", "question :"):
        assert marker in source
        assert marker.isascii()
    assert "\U0001f300" not in source


def test_e12_run_qa_subprocess_succeeds_without_pythonioencoding(tmp_path: Path) -> None:
    """E-12: 无 PYTHONIOENCODING 时 smoke 子进程仍 exit 0（Windows 控制台友好）."""
    graph_dir = tmp_path / "graphs-e12"
    graph_dir.mkdir()
    env = {key: value for key, value in os.environ.items() if key != "PYTHONIOENCODING"}
    env["LLM_MODE"] = "mock"
    env["GRAPH_DATA_DIR"] = str(graph_dir)
    result = subprocess.run(
        [
            sys.executable,
            str(RUN_QA_SCRIPT),
            "--smoke-m2",
            "--seed-demo-graph",
            "--graph-dir",
            str(graph_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env=env,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0, stderr or stdout
    assert "[OK]" in stdout or "citation" in stdout.lower()


def test_e12_run_patrol_help_exits_zero_without_encoding_crash() -> None:
    """E-12: run_patrol.py --help 子进程正常退出（Windows 控制台不因编码崩溃）."""
    result = subprocess.run(
        [sys.executable, str(RUN_PATROL_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    combined = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert "usage:" in combined.lower() or "patrol" in combined.lower()


# ---------------------------------------------------------------------------
# E-13 — 轮询 / status 孤儿
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e13_pipeline_status_unavailable_returns_409_envelope(api_client: AsyncClient) -> None:
    """E-13: 详情轮询依赖的 status 缺失 → 409 PIPELINE_STATUS_UNAVAILABLE + message."""
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus
    from backend.services.paper_service import get_paper_service

    service = get_paper_service()
    paper_id = "status-orphan-e13"
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="orphan",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    service._status.pop(paper_id, None)

    try:
        response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
        assert response.status_code == 409
        body = response.json()
        assert_error_envelope(body, code="PIPELINE_STATUS_UNAVAILABLE")
        assert "尚未初始化" in body["error"]["message"]
    finally:
        service._papers.pop(paper_id, None)


# ---------------------------------------------------------------------------
# E-14 — 空列表 / 空 insight 契约
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e14_papers_list_envelope_supports_empty_items_array(api_client: AsyncClient) -> None:
    """E-14: 文献列表响应含 items 数组（FE EmptyState 契约）."""
    response = await api_client.get("/api/v1/papers")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert isinstance(data["items"], list)
    assert "total" in data


@pytest.mark.asyncio
async def test_e14_three_branch_status_fixtures_for_fe_polling(api_client: AsyncClient) -> None:
    """E-14: ready / processing / failed 三态 fixture 与 FE 演示路径一致."""
    ready = await api_client.get(f"/api/v1/papers/{READY_ID}/status")
    processing = await api_client.get("/api/v1/papers/hss-002/status")
    failed = await api_client.get("/api/v1/papers/hss-failed-001/status")

    assert ready.json()["data"]["status"] == "ready"
    assert processing.json()["data"]["status"] == "processing"
    failed_data = failed.json()["data"]
    assert failed_data["status"] == "failed"
    assert failed_data["error_code"]
    assert failed_data["failed_during"]


@pytest.mark.asyncio
async def test_e14_patrol_functional_returns_non_empty_insights(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-14 功能对照：正常巡检返回结构化 insights（与空 insight FE 壳对比）."""
    seed_patrol_graphs(
        mock_llm_env,
        {
            READY_ID: ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": [READY_ID, "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 200
    insights = response.json()["data"]["insights"]
    assert len(insights) >= 1
    assert insights[0]["title"]
    assert insights[0]["summary"]


# ---------------------------------------------------------------------------
# E-15 — 网络 / 畸形请求不裸 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e15_patrol_malformed_json_returns_422_not_500(api_client: AsyncClient) -> None:
    """E-15: 畸形 JSON → 422（非 500）."""
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
        f"/api/v1/papers/{READY_ID}/qa/stream",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_e15_unknown_api_route_returns_404_not_500(api_client: AsyncClient) -> None:
    """E-15: 未知路由 → 404（非 500 裸奔）."""
    response = await api_client.get("/api/v1/no-such-resource-e15")
    assert response.status_code == 404
    assert response.status_code != 500
