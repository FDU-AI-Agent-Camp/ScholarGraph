"""Integration: re-extract escape hatch runs the full pipeline again."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE, EXTRACT_LLM_TIMEOUT_CODE
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_pipeline_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Isolated upload + graph dirs with LLM_MODE=mock."""
    upload_path = tmp_path / "uploads"
    graph_path = tmp_path / "graphs"
    upload_path.mkdir(parents=True, exist_ok=True)
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    from backend.services.paper_service import get_paper_service

    get_paper_service.cache_clear()
    yield upload_path, graph_path
    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Integration sample for re-extract.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.mark.asyncio
async def test_reextract_runs_pipeline_and_reaches_ready(
    mock_pipeline_env: tuple[Path, Path],
    sample_pdf: Path,
) -> None:
    """After a fallback run, force_reextract reruns the pipeline to READY."""
    _, graph_path = mock_pipeline_env
    from backend.services.paper_service import get_paper_service

    service = get_paper_service()
    paper_id = "reextract-integration-001"
    scheduled_tasks: list[asyncio.Task[None]] = []

    def _schedule_and_capture(paper_id: str, pdf_path: Path) -> asyncio.Task[None]:
        async def _run() -> None:
            await run_paper_pipeline(paper_id, pdf_path)

        task = asyncio.create_task(_run())
        scheduled_tasks.append(task)
        return task

    dest = sample_pdf.parent / "uploads" / f"{paper_id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(sample_pdf.read_bytes())

    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="integration paper",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    service._pdf_paths[paper_id] = dest

    # Simulate a previous fallback run: warnings + stale graph.
    service.record_extract_warnings(paper_id, [EXTRACT_LLM_TIMEOUT_CODE, EXTRACT_HEURISTIC_FALLBACK_CODE])
    stale_graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    GraphStore(base_dir=graph_path).save(stale_graph)

    # Force re-extract and run the pipeline synchronously inside the test.
    with patch("backend.services.reextract_service.schedule_paper_pipeline", side_effect=_schedule_and_capture):
        await service.force_reextract(paper_id)
        await asyncio.gather(*scheduled_tasks)

    status = await service.get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == []

    graph = GraphStore(base_dir=graph_path).load(paper_id)
    assert graph is not None
    assert graph.paper_id == paper_id
