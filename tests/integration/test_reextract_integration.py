# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Integration: re-extract escape hatch runs the full pipeline again."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE, EXTRACT_LLM_TIMEOUT_CODE
from backend.graph.state import STAGE_PERCENT
from backend.graph.store import GraphStore
from backend.graph.workflow import run_paper_pipeline
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm

from tests.helpers.persistence_testkit import restart_paper_service

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_pdf(persistence_env, tmp_path: Path) -> Path:
    pdf_path = persistence_env["upload_dir"] / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Integration sample for re-extract.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


async def _register_ready_paper(paper_id: str, pdf_path: Path) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create(paper_id, "integration paper", str(pdf_path), status=PaperStatus.READY)
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            stage=PipelineStage.READY,
            message="ready",
            updated_at=now,
        ),
    )


@pytest.mark.asyncio
async def test_reextract_runs_pipeline_and_reaches_ready(
    persistence_env,
    sample_pdf: Path,
) -> None:
    """After a fallback run, force_reextract reruns the pipeline to READY."""
    graph_path = persistence_env["graph_dir"]
    paper_id = "reextract-integration-001"
    scheduled_runs: list[tuple[str, Path]] = []

    def _schedule_and_capture(pid: str, pdf_path: Path) -> asyncio.Task[None]:
        scheduled_runs.append((pid, pdf_path))
        loop = asyncio.get_running_loop()
        return loop.create_task(asyncio.sleep(0))

    await _register_ready_paper(paper_id, sample_pdf)
    service = await restart_paper_service()

    service.record_extract_warnings(paper_id, [EXTRACT_LLM_TIMEOUT_CODE, EXTRACT_HEURISTIC_FALLBACK_CODE])
    stale_graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    GraphStore(base_dir=graph_path).save(stale_graph)

    with (
        patch("backend.services.reextract_service.schedule_paper_pipeline", side_effect=_schedule_and_capture),
        patch("backend.rag.wipe_vector_sweep.schedule_wipe_wave2_sweep", return_value=[]),
    ):
        await service.force_reextract(paper_id)

    from tests.conftest import mock_pipeline_node_services

    for pid, pdf_path in scheduled_runs:
        with mock_pipeline_node_services(pid):
            await run_paper_pipeline(pid, pdf_path)

    status = await service.get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == []

    graph = GraphStore(base_dir=graph_path).load(paper_id)
    assert graph is not None
    assert graph.paper_id == paper_id
