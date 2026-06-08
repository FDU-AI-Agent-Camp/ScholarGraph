"""HTTP API: F.2.2 heuristic fallback observability (X11 status contract)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.main import app
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_success_envelope

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _register_paper(paper_id: str, *, status: PaperStatus = PaperStatus.PROCESSING) -> None:
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="f22 api test",
        status=status,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_api_x11_ready_status_exposes_fallback_warning(api_client: AsyncClient) -> None:
    paper_id = "api-f22-ready-fallback-001"
    _register_paper(paper_id)
    get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    get_paper_service().record_extract_warnings(paper_id, [EXTRACT_HEURISTIC_FALLBACK_CODE])
    get_pipeline_status_service().mark_ready(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["status"] == "ready"
    assert data["stage"] == "ready"
    assert data["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_api_x11_extracting_stage_keeps_fallback_warning_visible(api_client: AsyncClient) -> None:
    paper_id = "api-f22-extracting-warn-001"
    _register_paper(paper_id)
    get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    get_paper_service().record_extract_warnings(paper_id, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage"] == "extracting"
    assert data["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_api_x11_failed_pipeline_has_no_extract_warnings(api_client: AsyncClient) -> None:
    paper_id = "api-f22-failed-no-warn-001"
    _register_paper(paper_id)
    get_pipeline_status_service().mark_failed(
        paper_id,
        message="图谱 LLM 抽取失败",
        error_code="PIPELINE_FAILED",
        failed_during=PipelineStage.EXTRACTING,
    )

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data.get("extract_warnings", []) == []
