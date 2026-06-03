"""错误处理：ServiceError → workflow state → status 快照与可读 message。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.graph import nodes
from backend.graph.state import WorkflowState
from backend.graph.workflow import _ensure_failed_status_persisted, run_paper_pipeline
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError
from backend.services.paper_service import get_paper_service

from tests.conftest import mock_pipeline_node_services
from tests.helpers.status_contract import assert_snapshot_matches_contract

pytestmark = pytest.mark.integration

STAGE_ERROR_CASES = [
    (
        "get_ingest_service",
        "ingest",
        ServiceError("INGEST_FAILED", "无法解析 PDF: corrupt"),
        PipelineStage.INGESTING,
    ),
    (
        "get_agent_service",
        "classify_paradigm",
        ServiceError("LLM_JSON_INVALID", "范式分类 JSON 无效"),
        PipelineStage.CLASSIFYING,
    ),
    (
        "get_agent_service",
        "extract_graph",
        ServiceError("PIPELINE_FAILED", "图谱抽取器未就绪"),
        PipelineStage.EXTRACTING,
    ),
]


@pytest.mark.parametrize(
    ("service_getter", "service_method", "error", "expected_stage"),
    STAGE_ERROR_CASES,
)
async def test_run_paper_pipeline_maps_service_error_to_status_snapshot(
    integration_paper: tuple[str, Path],
    service_getter: str,
    service_method: str,
    error: ServiceError,
    expected_stage: PipelineStage,
) -> None:
    paper_id, pdf_path = integration_paper

    with mock_pipeline_node_services(paper_id) as mocks:
        if service_method == "ingest":
            mocks["ingest"].ingest = AsyncMock(side_effect=error)
        elif service_method == "classify_paradigm":
            mocks["agent"].classify_paradigm = AsyncMock(side_effect=error)
        else:
            mocks["agent"].extract_graph = AsyncMock(side_effect=error)
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    assert final.get("error_code") == error.code
    assert final.get("error_message") == error.message

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.error_code == error.code
    assert status.failed_during == expected_stage
    assert status.message == error.message
    assert_snapshot_matches_contract(status)


async def test_store_failure_message_persisted_on_status(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    store_message = "建图收尾失败: disk full"

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["completion"].finalize = MagicMock(
            side_effect=ServiceError("PIPELINE_FAILED", store_message),
        )
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("error_code") == "PIPELINE_FAILED"
    status = await get_paper_service().get_status(paper_id)
    assert store_message in status.message
    assert status.failed_during == PipelineStage.STORING


async def test_fail_node_uses_default_code_when_missing_in_state(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, _ = integration_paper
    state = WorkflowState(
        paper_id=paper_id,
        stage=PipelineStage.CLASSIFYING,
        error_message="未带 code 的失败",
        message="未带 code 的失败",
        failed=True,
    )
    await nodes.fail_node(state)
    status = await get_paper_service().get_status(paper_id)
    assert status.error_code == PIPELINE_FAILED_CODE
    assert status.message == "未带 code 的失败"


async def test_ensure_failed_status_persisted_backfills_missing_error_code(
    integration_paper: tuple[str, Path],
) -> None:
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperStatusData

    paper_id, _ = integration_paper
    paper_svc = get_paper_service()
    paper_svc._status[paper_id] = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.FAILED,
        percent=0,
        stage=PipelineStage.FAILED,
        message="旧快照",
        updated_at=datetime.now(UTC),
        error_code=None,
        failed_during=None,
    )

    final = WorkflowState(
        paper_id=paper_id,
        failed=True,
        error_code="INGEST_FAILED",
        error_message="补写错误信息",
        failed_during=PipelineStage.INGESTING,
    )
    await _ensure_failed_status_persisted(paper_id, final)

    status = await get_paper_service().get_status(paper_id)
    assert status.error_code == "INGEST_FAILED"
    assert status.message == "补写错误信息"
    assert status.failed_during == PipelineStage.INGESTING


async def test_status_api_returns_failed_error_fields(
    integration_paper: tuple[str, Path],
) -> None:
    from backend.main import app
    from httpx import ASGITransport, AsyncClient

    paper_id, pdf_path = integration_paper
    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            side_effect=ServiceError("INGEST_FAILED", "API 层可见错误"),
        )
        await run_paper_pipeline(paper_id, pdf_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "INGEST_FAILED"
    assert data["failed_during"] == "ingesting"
    assert "API 层可见错误" in data["message"]
