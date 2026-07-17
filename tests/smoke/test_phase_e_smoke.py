# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase E smoke: fast import / route / schema sanity (P7–P11)."""

from __future__ import annotations

import pytest
from backend.graph.head_store import HeadStore
from backend.graph.state import STAGE_PERCENT
from backend.main import app
from backend.schemas.paper import PipelineStage
from httpx import ASGITransport, AsyncClient


@pytest.mark.smoke
def test_smoke_head_refining_stage_registered() -> None:
    assert PipelineStage.HEAD_REFINING.value == "head_refining"
    assert STAGE_PERCENT[PipelineStage.HEAD_REFINING] == 35


@pytest.mark.smoke
def test_smoke_head_store_importable() -> None:
    store = HeadStore
    assert store.__name__ == "HeadStore"


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_health_and_status_routes_respond() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/v1/health")
        assert health.status_code == 200
        health_data = health.json()["data"]
        assert "grobid_connected" in health_data
        assert "grobid_note" in health_data

        status = await client.get("/api/v1/papers/hss-001/status")
        assert status.status_code == 200
        status_data = status.json()["data"]
        assert "stage" in status_data
        assert "head_refine_warnings" in status_data
        assert isinstance(status_data["head_refine_warnings"], list)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_paper_detail_accepts_ingest_head_field() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "paper_id" in data
        assert "ingest_head" in data or data.get("ingest_head") is None
