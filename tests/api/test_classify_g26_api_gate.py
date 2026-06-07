"""G2.6–G2.7 API gate: classify_warnings on status/detail + OpenAPI contract."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.main import app
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_success_envelope

pytestmark = pytest.mark.integration

OPENAPI = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_g27_get_status_includes_classify_warnings_field(api_client: AsyncClient) -> None:
    paper_id = "g27-status-warnings"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="g27",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.CLASSIFYING,
        message="正在范式分类",
    )
    get_paper_service().record_classify_warnings(paper_id, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_g26_status_api_classify_warnings_is_list_of_strings(api_client: AsyncClient) -> None:
    paper_id = "g26-status-list-type"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="g26",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    get_pipeline_status_service().mark_ready(paper_id)
    get_paper_service().record_classify_warnings(
        paper_id,
        [CLASSIFIER_HEURISTIC_FALLBACK_CODE, "future_code"],
    )

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    warnings = response.json()["data"]["classify_warnings"]
    assert isinstance(warnings, list)
    assert all(isinstance(code, str) for code in warnings)


@pytest.mark.asyncio
async def test_g25_api_failed_pipeline_has_no_classify_warnings(api_client: AsyncClient) -> None:
    paper_id = "g25-failed-no-warn"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="failed",
        status=PaperStatus.FAILED,
        created_at=now,
        updated_at=now,
    )
    get_pipeline_status_service().mark_failed(
        paper_id,
        message="范式 LLM 分类失败",
        error_code="PIPELINE_FAILED",
        failed_during=PipelineStage.CLASSIFYING,
    )

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data.get("classify_warnings", []) == []


def test_g26_openapi_documents_classify_warnings_on_status_and_detail() -> None:
    text = OPENAPI.read_text(encoding="utf-8")
    assert "classify_warnings:" in text
    assert "PaperStatusData:" in text
    assert "PaperDetail:" in text
