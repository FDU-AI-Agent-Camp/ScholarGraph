# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""API gate: classify_warnings carries machine code only; user copy is FE-mapped."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.main import app
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

FROZEN_CODE = "classifier_heuristic_fallback"
FROZEN_MESSAGE = "触发分类启发式Fallback!"
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_api_frozen_human_message_constant() -> None:
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE == FROZEN_MESSAGE


def test_api_frozen_machine_code_constant() -> None:
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE == FROZEN_CODE


@pytest.mark.asyncio
async def test_api_status_returns_machine_code_not_user_message(api_client: AsyncClient) -> None:
    paper_id = "api-frozen-status-code"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="frozen status",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    await get_pipeline_status_service().mark_ready(paper_id)
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [FROZEN_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    body = response.json()

    assert response.status_code == 200
    warnings = body["data"]["classify_warnings"]
    assert warnings == [FROZEN_CODE]
    assert FROZEN_MESSAGE not in warnings
    assert FROZEN_MESSAGE not in json.dumps(body["data"], ensure_ascii=False)


@pytest.mark.asyncio
async def test_api_detail_returns_machine_code_with_separate_classification_reason(
    api_client: AsyncClient,
) -> None:
    paper_id = "api-frozen-detail-reason"
    now = datetime.now(UTC)
    heuristic_reason = "文本出现 benchmark、dataset 等线索，符合 STEM 论文的典型结构。"
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="frozen detail",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        paradigm=Paradigm.STEM,
        classification=ParadigmClassification(
            paradigm=Paradigm.STEM,
            confidence=0.82,
            reason=heuristic_reason,
        ),
    )
    await get_pipeline_status_service().mark_ready(paper_id)
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [FROZEN_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}")
    data = response.json()["data"]

    assert data["classify_warnings"] == [FROZEN_CODE]
    assert data["classification"]["reason"] == heuristic_reason
    assert data["classification"]["reason"] != FROZEN_MESSAGE
    assert FROZEN_MESSAGE not in data["classify_warnings"]


@pytest.mark.asyncio
async def test_api_classifying_poll_exposes_frozen_machine_code(api_client: AsyncClient) -> None:
    paper_id = "api-frozen-classifying-poll"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="poll",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    await get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.CLASSIFYING,
        message="正在范式分类",
    )
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [FROZEN_CODE])

    for _ in range(2):
        response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
        assert response.json()["data"]["classify_warnings"] == [FROZEN_CODE]


def test_api_classify_fallback_fixtures_match_frozen_code() -> None:
    for name in ("paper-detail-classify-fallback.json", "paper-status-classify-fallback.json"):
        payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        assert payload["data"]["classify_warnings"] == [FROZEN_CODE]
