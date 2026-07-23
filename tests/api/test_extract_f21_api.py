# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP API: F.2.1 extract path observability (extract_warnings on status)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.main import app
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_success_envelope

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _register_processing_paper(paper_id: str) -> None:
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="f21 api test",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_api_status_after_extract_fallback_shows_warning_code(api_client: AsyncClient) -> None:
    paper_id = "api-f21-fallback-001"
    _register_processing_paper(paper_id)
    await get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, [EXTRACT_HEURISTIC_FALLBACK_CODE])
    await get_pipeline_status_service().mark_ready(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["status"] == "ready"
    assert data["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_api_status_after_llm_success_has_empty_extract_warnings(api_client: AsyncClient) -> None:
    paper_id = "api-f21-llm-ok-001"
    _register_processing_paper(paper_id)
    await get_pipeline_status_service().mark_ready(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    assert response.json()["data"]["extract_warnings"] == []


@pytest.mark.asyncio
async def test_api_openapi_extract_warnings_field_documented() -> None:
    from pathlib import Path

    openapi = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    assert "extract_warnings:" in text
    assert "extract_heuristic_fallback" in text
