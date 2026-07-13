"""Tests for DB-backed ephemeral pipeline state (D6)."""

from __future__ import annotations

import pytest
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService
from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service


def _sample_preview(paper_id: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Preview", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )


@pytest.mark.asyncio
async def test_active_run_id_survives_service_restart(persistence_env) -> None:
    paper_id = "ephemeral-run-id"
    await register_test_paper(paper_id, status=PaperStatus.READY)
    service = PaperService()
    service.set_active_run_id(paper_id, "run-persist-001")

    restarted = await restart_paper_service()
    assert restarted.get_active_run_id(paper_id) == "run-persist-001"


@pytest.mark.asyncio
async def test_preview_graph_survives_service_restart(persistence_env) -> None:
    paper_id = "ephemeral-preview"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    preview = _sample_preview(paper_id)
    service = PaperService()
    service.save_preview_graph(paper_id, preview)
    service.mark_preview_available(paper_id)

    restarted = await restart_paper_service()
    loaded = restarted.get_preview_graph(paper_id)

    assert loaded is not None
    assert loaded.paper_id == paper_id
    assert loaded.nodes[0].id == "n1"
    assert restarted.is_preview_available(paper_id) is True


@pytest.mark.asyncio
async def test_clear_ephemeral_pipeline_state_removes_preview_and_run_id(persistence_env) -> None:
    paper_id = "ephemeral-clear"
    await register_test_paper(paper_id, status=PaperStatus.READY)
    service = PaperService()
    service.set_active_run_id(paper_id, "run-clear-me")
    service.save_preview_graph(paper_id, _sample_preview(paper_id))

    service.clear_ephemeral_pipeline_state(paper_id)

    assert service.get_active_run_id(paper_id) is None
    assert service.get_preview_graph(paper_id) is None


@pytest.mark.asyncio
async def test_pipeline_repository_clear_preview_graph(persistence_env) -> None:
    paper_id = "repo-clear-preview"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    repo = PipelineRepository()
    await repo.save_preview_graph(paper_id, _sample_preview(paper_id))

    await repo.clear_preview_graph(paper_id)

    assert await repo.get_preview_graph(paper_id) is None
