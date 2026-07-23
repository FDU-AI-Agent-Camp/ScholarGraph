# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP API: F.2.3 extract fallback warning contract (X13–X17, X20)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.agents.extract_constants import (
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.main import app
from backend.repositories.async_bridge import run_async
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


def _register_ready_paper(paper_id: str) -> None:
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="f23 api test",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    run_async(get_pipeline_status_service().mark_ready(paper_id))


@pytest.mark.asyncio
async def test_api_x17_get_paper_includes_extract_warnings(api_client: AsyncClient) -> None:
    paper_id = "api-f23-detail-fallback-001"
    _register_ready_paper(paper_id)
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_api_x19_get_paper_without_fallback_has_empty_warnings(api_client: AsyncClient) -> None:
    paper_id = "api-f23-detail-clean-001"
    _register_ready_paper(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 200
    assert response.json()["data"]["extract_warnings"] == []


@pytest.mark.asyncio
async def test_api_x14_fallback_machine_code_on_status(api_client: AsyncClient) -> None:
    paper_id = "api-f23-status-code-001"
    _register_ready_paper(paper_id)
    await get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, [EXTRACT_HEURISTIC_FALLBACK_CODE])
    await get_pipeline_status_service().mark_ready(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    assert response.json()["data"]["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]


def test_api_x15_frozen_human_message_constant() -> None:
    assert EXTRACT_HEURISTIC_FALLBACK_MESSAGE == "触发启发式Fallback!"


def test_api_x20_openapi_paper_detail_documents_extract_warnings() -> None:
    from pathlib import Path

    openapi = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    assert "PaperDetail:" in text
    assert "extract_warnings:" in text


@pytest.mark.asyncio
async def test_api_x16_status_and_detail_warnings_stay_consistent(api_client: AsyncClient) -> None:
    paper_id = "api-f23-consistent-001"
    _register_ready_paper(paper_id)
    await get_paper_warning_service().record(
        paper_id,
        WarningType.EXTRACT,
        [EXTRACT_HEURISTIC_FALLBACK_CODE, "other_code"],
    )

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    detail_resp = await api_client.get(f"/api/v1/papers/{paper_id}")

    status_warnings = status_resp.json()["data"]["extract_warnings"]
    detail_warnings = detail_resp.json()["data"]["extract_warnings"]
    assert status_warnings == detail_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE, "other_code"]


@pytest.mark.asyncio
async def test_api_x16_extracting_stage_exposes_fallback_before_ready(api_client: AsyncClient) -> None:
    paper_id = "api-f23-extracting-warn-001"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="f23 extracting",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    await get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
    )
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage"] == "extracting"
    assert data["extract_warnings"] == [EXTRACT_HEURISTIC_FALLBACK_CODE]
