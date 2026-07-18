# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
Phase G 红灯：classify_warnings 边界 — API 仅返回机器码，不含用户文案。

运行：uv run pytest -m red tests/api/test_classify_frozen_red.py -rx
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.main import app
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.red

FROZEN_MESSAGE = "触发分类启发式Fallback!"


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_red_api_status_classify_warnings_never_contains_user_message(
    api_client: AsyncClient,
) -> None:
    paper_id = "red-api-status-no-toast"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="red",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    get_pipeline_status_service().mark_ready(paper_id)
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    payload = json.dumps(response.json()["data"], ensure_ascii=False)

    assert response.json()["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert FROZEN_MESSAGE not in response.json()["data"]["classify_warnings"]
    assert FROZEN_MESSAGE not in payload


@pytest.mark.asyncio
async def test_red_api_detail_classify_warnings_never_contains_user_message(
    api_client: AsyncClient,
) -> None:
    paper_id = "red-api-detail-no-toast"
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="red detail",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    get_pipeline_status_service().mark_ready(paper_id)
    await get_paper_warning_service().record(paper_id, WarningType.CLASSIFY, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}")
    data = response.json()["data"]

    assert data["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE not in data["classify_warnings"]
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE not in json.dumps(data, ensure_ascii=False)
