# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP API: Phase G classify fallback warning contract (G2.6–G2.8)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
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
        title="g23 api test",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    run_async(get_pipeline_status_service().mark_ready(paper_id))


@pytest.mark.asyncio
async def test_api_g17_get_paper_includes_classify_warnings(api_client: AsyncClient) -> None:
    paper_id = "api-g23-detail-fallback-001"
    _register_ready_paper(paper_id)
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_api_g19_get_paper_without_fallback_has_empty_classify_warnings(api_client: AsyncClient) -> None:
    paper_id = "api-g23-detail-clean-001"
    _register_ready_paper(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 200
    assert response.json()["data"]["classify_warnings"] == []


@pytest.mark.asyncio
async def test_api_g14_fallback_machine_code_on_status(api_client: AsyncClient) -> None:
    paper_id = "api-g23-status-code-001"
    _register_ready_paper(paper_id)
    await get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.CLASSIFYING,
        message="正在范式分类",
    )
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    await get_pipeline_status_service().mark_ready(paper_id)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    assert response.json()["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_api_g15_frozen_human_message_constant() -> None:
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE == "触发分类启发式Fallback!"


def test_api_g20_openapi_documents_classify_warnings() -> None:
    from pathlib import Path

    openapi = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    assert "PaperDetail:" in text
    assert "classify_warnings:" in text


@pytest.mark.asyncio
async def test_api_g16_status_and_detail_classify_warnings_stay_consistent(api_client: AsyncClient) -> None:
    paper_id = "api-g23-consistent-001"
    _register_ready_paper(paper_id)
    await get_paper_warning_service().record(
        paper_id,
        WarningType.CLASSIFY,
        [CLASSIFIER_HEURISTIC_FALLBACK_CODE, "other_code"],
    )

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    detail_resp = await api_client.get(f"/api/v1/papers/{paper_id}")

    status_warnings = status_resp.json()["data"]["classify_warnings"]
    detail_warnings = detail_resp.json()["data"]["classify_warnings"]
    assert status_warnings == detail_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE, "other_code"]


@pytest.mark.asyncio
async def test_api_g16_classifying_stage_exposes_fallback_before_ready(api_client: AsyncClient) -> None:
    paper_id = "api-g23-classifying-warn-001"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="g23 classifying",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    await get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.CLASSIFYING,
        message="正在范式分类",
    )
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage"] == "classifying"
    assert data["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_api_g28_classification_unchanged_when_classify_warnings_present(api_client: AsyncClient) -> None:
    """G2.8: ParadigmClassification contract on detail stays independent of warnings."""
    from backend.schemas.paradigm import Paradigm, ParadigmClassification

    paper_id = "api-g28-classification-001"
    now = datetime.now(UTC)
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.88,
        reason="Theory-driven qualitative framing.",
    )
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="g28 api test",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        paradigm=Paradigm.HSS,
        classification=classification,
    )
    await get_pipeline_status_service().mark_ready(paper_id)
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert data["classification"]["paradigm"] == "HSS"
    assert data["classification"]["confidence"] == 0.88
    assert data["classification"]["reason"] == classification.reason
    assert set(data["classification"].keys()) == {"paradigm", "confidence", "reason"}
    assert "classify_warnings" not in data["classification"]
