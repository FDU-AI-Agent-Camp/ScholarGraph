"""HTTP API: force re-extract escape hatch (Plan C)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.main import app
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_pipeline_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Isolated upload + graph dirs and LLM_MODE=mock for re-extract tests."""
    from backend.services.paper_service import get_paper_service

    upload_path = tmp_path / "uploads"
    graph_path = tmp_path / "graphs"
    upload_path.mkdir(parents=True, exist_ok=True)
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    get_paper_service.cache_clear()
    yield upload_path, graph_path
    get_settings.cache_clear()
    get_paper_service.cache_clear()


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
    _, graph_path = mock_pipeline_env
    paper_id = await _upload_pdf(api_client, sample_pdf_path)

    service = get_paper_service()
    # Simulate a previous run that ended with a fallback warning.
    service.record_extract_warnings(paper_id, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["extract_warnings"] == []
    scheduler.assert_called_once_with(paper_id, service._pdf_paths[paper_id])

    # Graph store should not contain a final graph for this paper yet.
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

    service = get_paper_service()
    service._papers[paper_id] = service._papers[paper_id].model_copy(
        update={"status": PaperStatus.PROCESSING},
    )

    response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_ALREADY_PROCESSING"


@pytest.mark.asyncio
async def test_force_reextract_returns_404_for_unknown_paper(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/papers/nonexistent/reextract")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAPER_NOT_FOUND"
