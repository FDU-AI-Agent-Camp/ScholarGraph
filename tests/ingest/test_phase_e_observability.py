# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase E observability: head_refining stage + status warnings (P7/P8)."""

from __future__ import annotations

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.main import app
from backend.schemas.paper import PipelineStage
from httpx import ASGITransport, AsyncClient


def test_head_refining_stage_percent_mapping() -> None:
    assert STAGE_PERCENT[PipelineStage.HEAD_REFINING] == 35


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_status_api_includes_head_refine_warnings_field(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/hss-001/status")

    assert response.status_code == 200
    assert response.json()["data"]["head_refine_warnings"] == []
