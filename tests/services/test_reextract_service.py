"""Unit tests for the re-extract escape hatch service logic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from backend.api.exceptions import ApiError
from backend.db.base import get_async_session_factory
from backend.db.models import PaperRow
from backend.graph.head_store import HeadStore
from backend.graph.state import STAGE_PERCENT
from backend.graph.store import GraphStore
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService
from tests.helpers.persistence_testkit import restart_paper_service


@pytest.fixture
def sample_pdf(persistence_env, tmp_path: Path) -> Path:
    """Create a minimal valid 1-page PDF."""
    pdf_path = persistence_env["upload_dir"] / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample text for re-extract unit tests.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


async def _register_paper(
    paper_id: str,
    pdf_path: Path,
    *,
    status: PaperStatus,
) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create(paper_id, "unit test paper", str(pdf_path), status=status)
    now = datetime.now(UTC)
    if status == PaperStatus.PENDING:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=0,
            stage=None,
            message="pending",
            updated_at=now,
        )
    elif status == PaperStatus.PROCESSING:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=STAGE_PERCENT[PipelineStage.INGESTING],
            stage=PipelineStage.INGESTING,
            message="ingesting",
            updated_at=now,
        )
    elif status == PaperStatus.READY:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=STAGE_PERCENT[PipelineStage.READY],
            stage=PipelineStage.READY,
            message="ready",
            updated_at=now,
        )
    else:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=STAGE_PERCENT[PipelineStage.FAILED],
            stage=PipelineStage.FAILED,
            message="failed",
            updated_at=now,
            error_code="PIPELINE_FAILED",
        )
    await pipeline_repo.save_status(paper_id, snapshot)


async def _seed_previous_run(service: PaperService, paper_id: str) -> None:
    """Simulate a paper that has completed a fallback run."""
    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE, EXTRACT_LLM_TIMEOUT_CODE

    service.record_extract_warnings(paper_id, [EXTRACT_LLM_TIMEOUT_CODE, EXTRACT_HEURISTIC_FALLBACK_CODE])
    service.record_classify_warnings(paper_id, ["classifier_some_warning"])
    service.record_head_refine_warnings(paper_id, ["mineru_unavailable"])

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
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "reextract-unit-001"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()
    await _seed_previous_run(service, paper_id)

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        status = await service.force_reextract(paper_id)

    assert status.status == PaperStatus.PENDING
    assert status.percent == 0
    assert status.extract_warnings == []
    scheduler.assert_called_once_with(paper_id, sample_pdf)

    paper = await service.get_paper(paper_id)
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
    assert sample_pdf.is_file()

    async with get_async_session_factory()() as session:
        row = await session.get(PaperRow, paper_id)
    assert row is not None
    assert row.graph_version == "2"


@pytest.mark.asyncio
async def test_force_reextract_rejects_processing_paper(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "reextract-unit-processing"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.PROCESSING)
    service = await restart_paper_service()

    with pytest.raises(ApiError) as exc_info:
        await service.force_reextract(paper_id)

    assert exc_info.value.code == "PAPER_ALREADY_PROCESSING"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_force_reextract_overrides_409_with_force_true(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "reextract-unit-force-processing"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.PROCESSING)
    service = await restart_paper_service()
    abort = AsyncMock()

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline", abort),
        patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler,
    ):
        status = await service.force_reextract(paper_id, force=True)

    abort.assert_awaited_once_with(paper_id)
    assert status.status == PaperStatus.PENDING
    scheduler.assert_called_once_with(paper_id, sample_pdf)


@pytest.mark.asyncio
async def test_force_reextract_rejects_missing_pdf(persistence_env) -> None:
    paper_id = "reextract-unit-no-pdf"
    missing_pdf = persistence_env["upload_dir"] / "missing.pdf"
    await _register_paper(paper_id, missing_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()

    with pytest.raises(ApiError) as exc_info:
        await service.force_reextract(paper_id)

    assert exc_info.value.code == "PDF_NOT_FOUND"
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_force_reextract_allows_failed_paper(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "reextract-unit-failed"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.FAILED)
    service = await restart_paper_service()

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        status = await service.force_reextract(paper_id)

    assert status.status == PaperStatus.PENDING
    scheduler.assert_called_once()


@pytest.mark.asyncio
async def test_force_reextract_is_idempotent_from_ready(
    persistence_env,
    sample_pdf: Path,
) -> None:
    """Calling re-extract twice from READY should reset twice; PDF must remain."""
    paper_id = "reextract-unit-idempotent"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        await service.force_reextract(paper_id)
        await service.force_reextract(paper_id)

    assert scheduler.call_count == 2
    assert sample_pdf.is_file()

    async with get_async_session_factory()() as session:
        row = await session.get(PaperRow, paper_id)
    assert row is not None
    assert row.graph_version == "3"
