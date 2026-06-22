"""Red-light / boundary tests for the re-extract escape hatch API."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import fitz
import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.main import app
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.red]


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
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
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Red test PDF.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _register_paper(
    paper_id: str,
    *,
    status: PaperStatus,
    pdf_path: Path | None = None,
    warnings: list[str] | None = None,
) -> None:
    service = get_paper_service()
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="red test",
        status=status,
        created_at=now,
        updated_at=now,
    )
    pss = get_pipeline_status_service()
    if status == PaperStatus.READY:
        pss.mark_ready(paper_id, message="red setup")
    elif status == PaperStatus.FAILED:
        pss.mark_failed(paper_id, message="red setup", error_code="PIPELINE_FAILED")
    else:
        pss.start_processing(paper_id, message="red setup")
    if pdf_path is not None:
        service._pdf_paths[paper_id] = pdf_path
    if warnings:
        service.record_extract_warnings(paper_id, warnings)


@pytest.mark.asyncio
async def test_red_reextract_unknown_paper_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/papers/unknown-paper/reextract")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAPER_NOT_FOUND"


@pytest.mark.asyncio
async def test_red_reextract_processing_paper_returns_409(
    api_client: AsyncClient,
    mock_env: tuple[Path, Path],
    sample_pdf: Path,
) -> None:
    paper_id = "red-reextract-processing"
    _register_paper(paper_id, status=PaperStatus.PROCESSING, pdf_path=sample_pdf)

    response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_ALREADY_PROCESSING"


@pytest.mark.asyncio
async def test_red_reextract_missing_pdf_returns_422(
    api_client: AsyncClient,
    mock_env: tuple[Path, Path],
) -> None:
    paper_id = "red-reextract-missing-pdf"
    _register_paper(paper_id, status=PaperStatus.READY)

    response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_NOT_FOUND"


@pytest.mark.asyncio
async def test_red_reextract_from_ready_clears_graph_and_warnings(
    api_client: AsyncClient,
    mock_env: tuple[Path, Path],
    sample_pdf: Path,
) -> None:
    _, graph_path = mock_env
    paper_id = "red-reextract-clears-artefacts"
    _register_paper(
        paper_id,
        status=PaperStatus.READY,
        pdf_path=sample_pdf,
        warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
    )

    from backend.graph.store import GraphStore

    GraphStore(base_dir=graph_path).save(
        UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
            edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
        ),
    )

    response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["extract_warnings"] == []
    assert GraphStore(base_dir=graph_path).load(paper_id) is None


@pytest.mark.asyncio
async def test_red_reextract_allows_failed_paper(
    api_client: AsyncClient,
    mock_env: tuple[Path, Path],
    sample_pdf: Path,
) -> None:
    paper_id = "red-reextract-failed"
    _register_paper(paper_id, status=PaperStatus.FAILED, pdf_path=sample_pdf)

    response = await api_client.post(f"/api/v1/papers/{paper_id}/reextract")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
