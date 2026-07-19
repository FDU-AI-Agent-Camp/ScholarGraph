# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""P8: head_refine_warnings exposed on PaperStatusData and GET /papers/{id}/status."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.main import app
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.head_refine_wait import HEAD_REFINE_TIMEOUT_WARNING
from backend.services.paper_service import get_paper_service
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_get_status_includes_head_refine_warnings_after_apply(
    registered_paper: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.config import get_settings

    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    service = get_paper_service()
    service.apply_head_refine(
        registered_paper,
        merged=IngestHead(title="Refined"),
        classifier_input="Title: Refined",
        warnings=["mineru_unavailable"],
    )

    status = await service.get_status(registered_paper)

    assert status.head_refine_warnings == ["mineru_unavailable"]


@pytest.mark.asyncio
async def test_record_head_refine_warnings_merges_without_duplicates(registered_paper: str) -> None:
    service = get_paper_service()
    await get_paper_warning_service().record(registered_paper, WarningType.HEAD_REFINE, ["mineru_unavailable"])
    await get_paper_warning_service().record(
        registered_paper, WarningType.HEAD_REFINE, ["head_refine_timeout", "mineru_unavailable"]
    )

    status = await service.get_status(registered_paper)

    assert status.head_refine_warnings == ["mineru_unavailable", HEAD_REFINE_TIMEOUT_WARNING]


@pytest.mark.asyncio
async def test_status_api_returns_head_refine_warnings(
    registered_paper: str,
    api_client: AsyncClient,
) -> None:
    """HTTP status must read warnings from the same isolated DB as ``record``."""
    await get_paper_warning_service().record(
        registered_paper,
        WarningType.HEAD_REFINE,
        ["grobid_unavailable"],
    )

    response = await api_client.get(f"/api/v1/papers/{registered_paper}/status")

    assert response.status_code == 200
    assert response.json()["data"]["head_refine_warnings"] == ["grobid_unavailable"]


@pytest.mark.asyncio
async def test_status_snapshot_carries_warnings_on_stage_advance(registered_paper: str) -> None:
    service = get_paper_service()
    await get_paper_warning_service().record(registered_paper, WarningType.HEAD_REFINE, ["mineru_disabled"])
    service.set_status_snapshot(
        registered_paper,
        status=PaperStatus.PROCESSING,
        stage=PipelineStage.CLASSIFYING,
        percent=50,
        message="正在识别范式与理论视角…",
    )

    status = await service.get_status(registered_paper)

    assert status.stage == PipelineStage.CLASSIFYING
    assert status.head_refine_warnings == ["mineru_disabled"]
