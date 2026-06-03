"""V1 DoD §6.5 — 前后端联调红灯路径与功能可用性（BE 侧）.

与 ``frontend/src/test/v1-dod-fe-be-red-paths.integration.test.ts`` 成对：
验证 HTTP 契约、边界输入、异常 envelope 与用户可读 message，并覆盖若干绿灯功能路径。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.graph.store import GraphStore
from backend.llm.mock_chat import MOCK_DISCLAIMER, MOCK_PATROL_PREFIX
from backend.services.paper_service import MAX_UPLOAD_BYTES, get_paper_service
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.helpers.patrol_graphs import (
    build_hss_graph_with_thesis,
    build_hss_graph_without_thesis,
    seed_patrol_graphs,
)

VALID_PDF = b"%PDF-1.4\n% FE-BE red paths upload test"


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
# 功能可用 — 上传 → pending 与 Mock 巡检/问答
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fe_be_green_upload_returns_pending_with_poll_hint(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """绿灯：合法 PDF 上传 201 + pending + 轮询提示（与 FE upload 流程对齐）."""
    from backend.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("sample.pdf", VALID_PDF, "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["status"] == "pending"
    assert body["data"]["paper_id"]
    assert "自动解构" in body["data"]["message"]


@pytest.mark.asyncio
async def test_fe_be_upload_pipeline_reaches_ready(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple,
) -> None:
    """上传后自动流水线（mock）应到达 ready，供 FE 详情轮询联调。"""
    import asyncio

    from tests.api.test_papers_upload import VALID_PDF

    from tests.helpers.upload_pipeline_mock import mock_http_upload_pipeline_run

    with mock_http_upload_pipeline_run():
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("fe-be-pipeline.pdf", VALID_PDF, "application/pdf")},
        )
        assert create.status_code == 201
        paper_id = create.json()["data"]["paper_id"]

        final_status = "pending"
        for _ in range(120):
            await asyncio.sleep(0.05)
            status = await api_client.get(f"/api/v1/papers/{paper_id}/status")
            final_status = status.json()["data"]["status"]
            if final_status in ("ready", "failed"):
                break

        assert final_status == "ready"


@pytest.mark.asyncio
async def test_fe_be_mock_patrol_summary_contains_mock_prefix(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-10 功能：mock 模式巡检成功且 summary 含 Mock 前缀（FE 可展示 disclaimer）."""
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
    summary = response.json()["data"]["insights"][0]["summary"]
    assert MOCK_PATROL_PREFIX in summary or "分析视角" in summary


@pytest.mark.asyncio
async def test_fe_be_mock_qa_stream_contains_disclaimer(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-10 功能：mock QA SSE 含 MOCK_DISCLAIMER（与 FE detail 展示对齐）."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "核心论点是什么？"},
    )
    assert response.status_code == 200
    messages = "".join(payload["delta"] for name, payload in _parse_sse(response.text) if name == "message")
    assert MOCK_DISCLAIMER in messages


# ---------------------------------------------------------------------------
# E-02 / E-03 — Papers 404 与上传边界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e02_paper_not_found_message_on_graph_and_qa(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-02: 不存在论文在 graph / qa 均 404 PAPER_NOT_FOUND + 可读 message."""
    _ = mock_llm_env
    ghost = "ghost-paper-fe-be-404"

    graph_resp = await api_client.get(f"/api/v1/papers/{ghost}/graph")
    assert graph_resp.status_code == 404
    graph_body = graph_resp.json()
    assert_error_envelope(graph_body, code="PAPER_NOT_FOUND")
    assert graph_body["error"]["message"]

    qa_resp = await api_client.post(
        f"/api/v1/papers/{ghost}/qa/stream",
        json={"question": "测试"},
    )
    assert qa_resp.status_code == 404
    assert_error_envelope(qa_resp.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_e03_oversized_upload_returns_ingest_failed_with_size_hint(
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-03: 超过 32MB → 400 INGEST_FAILED + 大小限制文案."""
    from backend.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    oversized = b"%PDF" + b"x" * (MAX_UPLOAD_BYTES + 1)
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("big.pdf", oversized, "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    assert_error_envelope(body, code="INGEST_FAILED")
    assert "32MB" in body["error"]["message"]


# ---------------------------------------------------------------------------
# E-06 — Patrol 矛盾模式与 LLM 回退
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e06_patrol_contradiction_insufficient_thesis_422(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06: contradiction 缺 Thesis → 422 PATROL_INSUFFICIENT_DATA."""
    store = GraphStore(base_dir=mock_llm_env)
    store.save(build_hss_graph_without_thesis("hss-001"))
    store.save(
        build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_thesis_b",
            thesis_label="论点 B",
        ),
    )

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "contradiction"},
    )
    assert response.status_code == 422
    assert_error_envelope(response.json(), code="PATROL_INSUFFICIENT_DATA")


@pytest.mark.asyncio
async def test_e10_patrol_llm_failure_falls_back_to_template_not_500(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-10 红灯：LLM 摘要失败 → 200 + 模板 fallback（非 500）."""
    seed_patrol_graphs(
        mock_llm_env,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    with patch(
        "backend.patrol.lens_clash.generate_patrol_summary",
        new=AsyncMock(return_value=None),
    ):
        response = await api_client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
        )

    assert response.status_code == 200
    summary = response.json()["data"]["insights"][0]["summary"]
    assert "分析视角" in summary or "消费社会" in summary
    assert MOCK_PATROL_PREFIX not in summary


# ---------------------------------------------------------------------------
# E-07 / E-13 — QA 校验与 status 孤儿
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e07_qa_empty_question_returns_422_not_500(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-07: 空 question → 422 校验错误（非 500）."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": ""},
    )
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_e13_pipeline_status_unavailable_returns_409_envelope(
    api_client: AsyncClient,
) -> None:
    """E-13: status 快照缺失 → 409 PIPELINE_STATUS_UNAVAILABLE + 中文 message."""
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus
    from backend.services.paper_service import get_paper_service

    service = get_paper_service()
    paper_id = "status-orphan-fe-be"
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
# E-14 — 三态 fixture 与 FE 轮询契约
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e14_three_branch_status_fixtures_match_fe_demo_path(
    api_client: AsyncClient,
) -> None:
    """E-14: hss-001/002/failed-001 三态与 docs/api/fixtures 一致."""
    ready = await api_client.get("/api/v1/papers/hss-001/status")
    processing = await api_client.get("/api/v1/papers/hss-002/status")
    failed = await api_client.get("/api/v1/papers/hss-failed-001/status")

    assert ready.json()["data"]["status"] == "ready"
    assert processing.json()["data"]["status"] == "processing"
    failed_data = failed.json()["data"]
    assert failed_data["status"] == "failed"
    assert failed_data["error_code"] == "LLM_JSON_INVALID"
    assert failed_data["failed_during"] == "classifying"


@pytest.mark.asyncio
async def test_e06_patrol_unknown_paper_id_returns_graph_not_ready_not_500(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """E-06 红灯：引用不存在 paper_id → 409 GRAPH_NOT_READY（非 500）."""
    _ = mock_llm_env
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["ghost-a", "ghost-b"], "mode": "lens_clash"},
    )
    assert response.status_code == 409
    assert_error_envelope(response.json(), code="GRAPH_NOT_READY")
