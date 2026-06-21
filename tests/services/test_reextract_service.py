"""Unit tests for the re-extract escape hatch service logic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from backend.api.exceptions import ApiError
from backend.graph.head_store import HeadStore
from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PaperService:
    """Fresh PaperService with isolated graph/upload dirs."""
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path / "graphs"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    from backend.config import get_settings

    get_settings.cache_clear()
    return PaperService()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal valid 1-page PDF."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample text for re-extract unit tests.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _register_paper(service: PaperService, paper_id: str, *, status: PaperStatus) -> None:
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="unit test paper",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _seed_previous_run(service: PaperService, paper_id: str) -> None:
    """Simulate a paper that has completed a fallback run."""
    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE, EXTRACT_LLM_TIMEOUT_CODE

    service.record_extract_warnings(paper_id, [EXTRACT_LLM_TIMEOUT_CODE, EXTRACT_HEURISTIC_FALLBACK_CODE])
    service.record_classify_warnings(paper_id, ["classifier_some_warning"])
    service.record_head_refine_warnings(paper_id, ["mineru_unavailable"])
    service._refined_head[paper_id] = IngestHead(title="T", abstract="A", intro="I")
    service._refined_classifier_input[paper_id] = "previous input"

    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    GraphStore().save(graph)
    HeadStore().save(paper_id, merged=IngestHead(title="T", abstract="A", intro="I"))
    service.save_preview_graph(paper_id, graph)
    service.mark_preview_available(paper_id)


@pytest.mark.asyncio
async def test_force_reextract_clears_state_and_requeues_pipeline(
    service: PaperService,
    sample_pdf: Path,
) -> None:
    paper_id = "reextract-unit-001"
    _register_paper(service, paper_id, status=PaperStatus.READY)
    service._pdf_paths[paper_id] = sample_pdf
    _seed_previous_run(service, paper_id)

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        status = await service.force_reextract(paper_id)

    assert status.status == PaperStatus.PENDING
    assert status.percent == 0
    assert status.extract_warnings == []
    scheduler.assert_called_once_with(paper_id, sample_pdf)

    paper = service._papers[paper_id]
    assert paper.status == PaperStatus.PENDING
    assert paper.paradigm is None
    assert paper.classification is None
    assert paper.preview_available is False
    assert service.get_extract_warnings(paper_id) == []
    assert service.get_classify_warnings(paper_id) == []
    assert service.get_head_refine_warnings(paper_id) == []
    assert service.get_preview_graph(paper_id) is None
    assert service.is_preview_available(paper_id) is False
    assert GraphStore().load(paper_id) is None
    assert HeadStore().load(paper_id) is None
    assert sample_pdf.is_file()  # PDF itself must survive


@pytest.mark.asyncio
async def test_force_reextract_rejects_processing_paper(
    service: PaperService,
    sample_pdf: Path,
) -> None:
    paper_id = "reextract-unit-processing"
    _register_paper(service, paper_id, status=PaperStatus.PROCESSING)
    service._pdf_paths[paper_id] = sample_pdf

    with pytest.raises(ApiError) as exc_info:
        await service.force_reextract(paper_id)

    assert exc_info.value.code == "PAPER_ALREADY_PROCESSING"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_force_reextract_rejects_missing_pdf(service: PaperService) -> None:
    paper_id = "reextract-unit-no-pdf"
    _register_paper(service, paper_id, status=PaperStatus.READY)

    with pytest.raises(ApiError) as exc_info:
        await service.force_reextract(paper_id)

    assert exc_info.value.code == "PDF_NOT_FOUND"
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_force_reextract_allows_failed_paper(
    service: PaperService,
    sample_pdf: Path,
) -> None:
    paper_id = "reextract-unit-failed"
    _register_paper(service, paper_id, status=PaperStatus.FAILED)
    service._pdf_paths[paper_id] = sample_pdf

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        status = await service.force_reextract(paper_id)

    assert status.status == PaperStatus.PENDING
    scheduler.assert_called_once()


@pytest.mark.asyncio
async def test_force_reextract_is_idempotent_from_ready(
    service: PaperService,
    sample_pdf: Path,
) -> None:
    """Calling re-extract twice from READY should reset twice; PDF must remain."""
    paper_id = "reextract-unit-idempotent"
    _register_paper(service, paper_id, status=PaperStatus.READY)
    service._pdf_paths[paper_id] = sample_pdf

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        await service.force_reextract(paper_id)
        await service.force_reextract(paper_id)

    assert scheduler.call_count == 2
    assert sample_pdf.is_file()
