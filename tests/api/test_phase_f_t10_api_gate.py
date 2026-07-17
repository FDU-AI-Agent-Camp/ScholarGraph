# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""F.6 acceptance gate T10: extract_warnings API contract on status + OpenAPI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
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
async def test_t10_get_status_includes_extract_warnings_field(api_client: AsyncClient) -> None:
    paper_id = "t10-status-warnings"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="t10",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    get_paper_service().record_extract_warnings(paper_id, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


def test_t10_openapi_documents_extract_warnings_on_status_and_detail() -> None:
    text = OPENAPI.read_text(encoding="utf-8")
    assert "extract_warnings:" in text
    assert "extract_heuristic_fallback" in text
    assert "PaperStatusData:" in text
    assert "PaperDetail:" in text
