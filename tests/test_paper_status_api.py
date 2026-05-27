"""HTTP integration: GET /papers/{id}/status returns api-contract-compliant payloads."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.graph.state import STAGE_PERCENT
from backend.main import app
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.pipeline_status_service import validate_status_contract


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _assert_body_contract(body: dict) -> None:
    data = body["data"]
    status = PaperStatus(data["status"])
    stage = PipelineStage(data["stage"]) if data.get("stage") is not None else None
    validate_status_contract(status=status, stage=stage, percent=data["percent"])


async def test_status_ready_fixture_matches_contract(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/hss-001/status")
    assert response.status_code == 200
    body = response.json()
    _assert_body_contract(body)
    assert body["data"]["status"] == "ready"
    assert body["data"]["stage"] == "ready"
    assert body["data"]["percent"] == 100


async def test_status_processing_fixture_matches_contract(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/hss-002/status")
    assert response.status_code == 200
    body = response.json()
    _assert_body_contract(body)
    assert body["data"]["status"] == "processing"
    assert body["data"]["stage"] == "classifying"
    assert body["data"]["percent"] == STAGE_PERCENT[PipelineStage.CLASSIFYING]


async def test_status_not_found_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/does-not-exist/status")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAPER_NOT_FOUND"
