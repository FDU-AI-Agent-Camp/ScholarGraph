"""End-to-end HTTP: upload → status poll → graph access matrix (FE↔BE 联调路径)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.services.paper_service import get_paper_service
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope, assert_success_envelope

VALID_PDF = b"%PDF-1.4\n% integration route test"


@pytest.fixture
async def api_client():
    from backend.main import app
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.mark.asyncio
async def test_upload_poll_status_then_graph_matrix(api_client, upload_dir) -> None:
    """Happy path: POST → pending status → graph 409 until ready."""
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("route.pdf", VALID_PDF, "application/pdf")},
    )
    assert create.status_code == 201
    paper_id = create.json()["data"]["paper_id"]

    status = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert status.status_code == 200
    assert status.json()["data"]["status"] == "pending"

    graph = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph.status_code == 409
    assert_error_envelope(graph.json(), code="GRAPH_NOT_READY")


@pytest.mark.asyncio
async def test_upload_invalid_pdf_does_not_create_pollable_paper(api_client, upload_dir) -> None:
    before_ids = set(get_paper_service()._papers.keys())

    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("bad.pdf", b"corrupt", "application/pdf")},
    )
    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")

    after_ids = set(get_paper_service()._papers.keys())
    assert after_ids == before_ids


@pytest.mark.asyncio
async def test_status_pipeline_uninitialized_returns_409(api_client) -> None:
    """Paper exists but status snapshot missing (non-pending) → PIPELINE_STATUS_UNAVAILABLE."""
    service = get_paper_service()
    paper_id = "status-orphan-001"
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="orphan",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    service._status.pop(paper_id, None)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PIPELINE_STATUS_UNAVAILABLE"
    assert "尚未初始化" in response.json()["error"]["message"]

    service._papers.pop(paper_id, None)


@pytest.mark.asyncio
async def test_three_branch_status_fixtures_support_fe_polling(api_client) -> None:
    """Align with FE demo paths: hss-001 ready, hss-002 processing, hss-failed-001 failed."""
    ready = await api_client.get("/api/v1/papers/hss-001/status")
    processing = await api_client.get("/api/v1/papers/hss-002/status")
    failed = await api_client.get("/api/v1/papers/hss-failed-001/status")

    assert ready.json()["data"]["status"] == "ready"
    assert processing.json()["data"]["status"] == "processing"
    assert failed.json()["data"]["status"] == "failed"
    assert failed.json()["data"]["error_code"] == "LLM_JSON_INVALID"

    graph_ready = await api_client.get("/api/v1/papers/hss-001/graph")
    graph_processing = await api_client.get("/api/v1/papers/hss-002/graph")
    assert graph_ready.status_code == 200
    assert_success_envelope(graph_ready.json())
    assert graph_processing.status_code == 409
