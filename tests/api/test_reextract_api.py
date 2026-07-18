# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP API: force re-extract escape hatch (Plan C)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.main import app
from backend.services.paper_warning_service import WarningType, get_paper_warning_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient
from tests.helpers.persistence_testkit import init_isolated_database, reset_persistence_singletons

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_pipeline_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Isolated upload + graph dirs, SQLite DB, and LLM_MODE=mock for re-extract tests."""
    upload_path = tmp_path / "uploads"
    graph_path = tmp_path / "graphs"
    db_path = tmp_path / "scholargraph.db"
    upload_path.mkdir(parents=True, exist_ok=True)
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    monkeypatch.setenv("LLM_MODE", "mock")
    reset_persistence_singletons()
    asyncio.run(init_isolated_database(db_path))
    yield upload_path, graph_path
    reset_persistence_singletons()
    get_settings.cache_clear()


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a minimal valid 1-page PDF for upload."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This is a sample paper for re-extract testing.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


async def _upload_pdf(api_client: AsyncClient, pdf_path: Path) -> str:
    with patch("backend.services.paper_service.schedule_paper_pipeline") as scheduler:
        with pdf_path.open("rb") as f:
            response = await api_client.post(
                "/api/v1/papers",
                files={"file": ("sample.pdf", f, "application/pdf")},
            )
    assert response.status_code == 201
    scheduler.assert_called_once()
    return response.json()["data"]["paper_id"]


@pytest.mark.asyncio
async def test_force_reextract_resets_status_and_clears_warnings(
    api_client: AsyncClient,
    mock_pipeline_env: tuple[Path, Path],
    sample_pdf_path: Path,
) -> None:
    """POST /papers/{id}/reextract clears artefacts and re-queues the pipeline."""
    upload_path, graph_path = mock_pipeline_env
    paper_id = await _upload_pdf(api_client, sample_pdf_path)

    from backend.services.paper_service import get_paper_service

    get_paper_service()
    await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline", AsyncMock()),
        patch(
            "backend.services.reextract_service.resolve_vector_store_for_delete",
            return_value=AsyncMock(delete_by_paper=AsyncMock()),
        ),
        patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler,
    ):
        response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["extract_warnings"] == []
    scheduler.assert_called_once_with(paper_id, upload_path / f"{paper_id}.pdf")

    from backend.graph.store import GraphStore

    assert GraphStore(base_dir=graph_path).load(paper_id) is None


@pytest.mark.asyncio
async def test_force_reextract_rejects_processing_paper(
    api_client: AsyncClient,
    mock_pipeline_env: tuple[Path, Path],
    sample_pdf_path: Path,
) -> None:
    """Re-extract is blocked while the paper is already processing."""
    paper_id = await _upload_pdf(api_client, sample_pdf_path)
    get_pipeline_status_service().start_processing(paper_id)

    response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_ALREADY_PROCESSING"


@pytest.mark.asyncio
async def test_force_reextract_processing_with_force_query(
    api_client: AsyncClient,
    mock_pipeline_env: tuple[Path, Path],
    sample_pdf_path: Path,
) -> None:
    """``?force=true`` aborts PROCESSING, purges vectors, and re-queues."""
    paper_id = await _upload_pdf(api_client, sample_pdf_path)
    get_pipeline_status_service().start_processing(paper_id)

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()
    abort = AsyncMock()

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline", abort),
        patch(
            "backend.services.reextract_service.resolve_vector_store_for_delete",
            return_value=vector_store,
        ),
        patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler,
    ):
        response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract?force=true")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    abort.assert_awaited_once_with(paper_id)
    vector_store.delete_by_paper.assert_awaited_once_with(paper_id)
    scheduler.assert_called_once()


@pytest.mark.asyncio
async def test_force_reextract_rejects_indexing_paper(
    api_client: AsyncClient,
    mock_pipeline_env: tuple[Path, Path],
    sample_pdf_path: Path,
) -> None:
    """Re-extract is blocked while the paper is indexing vectors."""
    paper_id = await _upload_pdf(api_client, sample_pdf_path)
    get_pipeline_status_service().mark_indexing(paper_id)

    response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_ALREADY_PROCESSING"


@pytest.mark.asyncio
async def test_force_reextract_returns_404_for_unknown_paper(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/papers/nonexistent/reextract")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAPER_NOT_FOUND"
