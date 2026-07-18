# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP API: Phase F observability — extract_warnings on status (X13–X17)."""

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


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _register_paper(paper_id: str) -> None:
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="extract observability api test",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_status_api_extracting_stage_exposes_extract_warnings_field(api_client: AsyncClient) -> None:
    paper_id = "api-extract-warn-001"
    _register_paper(paper_id)
    get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["stage"] == "extracting"
    assert "extract_warnings" in data
    assert data["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_ready_fixture_status_includes_extract_warnings_field(api_client: AsyncClient) -> None:
    paper_id = "api-extract-warn-clean-001"
    _register_paper(paper_id)
    get_pipeline_status_service().mark_ready(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "extract_warnings" in data
    assert isinstance(data["extract_warnings"], list)
    assert data["extract_warnings"] == []


@pytest.mark.asyncio
async def test_status_api_extract_warnings_is_list_of_strings(api_client: AsyncClient) -> None:
    paper_id = "api-extract-warn-002"
    _register_paper(paper_id)
    get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    await get_paper_warning_service().record(
        paper_id,
        WarningType.EXTRACT,
        [EXTRACT_HEURISTIC_FALLBACK_CODE],
    )

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    warnings = response.json()["data"]["extract_warnings"]
    assert isinstance(warnings, list)
    assert all(isinstance(code, str) for code in warnings)
