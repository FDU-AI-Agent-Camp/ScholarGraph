"""Phase G: classify_warnings on PaperStatusData and GET /papers/{id}/status."""

from __future__ import annotations

import pytest
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.main import app
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_record_classify_warnings_merges_without_duplicates(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_classify_warnings(registered_paper, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    service.record_classify_warnings(
        registered_paper,
        [CLASSIFIER_HEURISTIC_FALLBACK_CODE, "other_code"],
    )

    status = await service.get_status(registered_paper)

    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE, "other_code"]


@pytest.mark.asyncio
async def test_get_status_includes_classify_warnings_after_record(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_classify_warnings(registered_paper, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    status = await service.get_status(registered_paper)

    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_status_snapshot_carries_classify_warnings_on_stage_advance(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_classify_warnings(registered_paper, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    service.set_status_snapshot(
        registered_paper,
        status=PaperStatus.READY,
        stage=PipelineStage.READY,
        percent=100,
        message="建图完成",
    )

    status = await service.get_status(registered_paper)

    assert status.stage == PipelineStage.READY
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_status_api_returns_classify_warnings(
    api_client: AsyncClient,
    registered_paper: str,
) -> None:
    paper_id = registered_paper
    get_paper_service().record_classify_warnings(paper_id, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    assert response.json()["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_get_paper_includes_classify_warnings_on_detail(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_classify_warnings(registered_paper, [CLASSIFIER_HEURISTIC_FALLBACK_CODE])

    paper = await service.get_paper(registered_paper)

    assert paper.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
