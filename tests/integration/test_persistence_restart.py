"""Integration tests: upload → ready → restart → list still present."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.pipeline_completion_service import PipelineCompletionService
from httpx import AsyncClient

from tests.helpers.persistence_testkit import restart_paper_service

VALID_PDF = b"%PDF-1.4\n% persistence restart test"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upload_ready_survives_service_restart(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_dir = persistence_env["upload_dir"]
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)

    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("restart.pdf", VALID_PDF, "application/pdf")},
    )
    assert create.status_code == 201
    paper_id = create.json()["data"]["paper_id"]

    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="integration")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Claim", type="Thesis")],
        edges=[
            GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF"),
        ],
    )
    persistence = MagicMock(spec=GraphPersistenceService)
    completion = PipelineCompletionService(graph_persistence=persistence)
    completion.finalize(
        paper_id,
        graph_data=graph.model_dump(mode="json"),
        classification_data=classification.model_dump(mode="json"),
    )

    service = await restart_paper_service()
    items, total = await service.list_papers()
    assert total >= 1
    assert any(item.paper_id == paper_id for item in items)

    detail = await service.get_paper(paper_id)
    assert detail.status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS)
    assert (upload_dir / f"{paper_id}.pdf").is_file()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_status_persists_across_restart(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("status-restart", "Status", str(persistence_env["upload_dir"] / "x.pdf"))
    from backend.repositories.pipeline_repository import PipelineRepository

    pipeline_repo = PipelineRepository()
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "status-restart",
        PaperStatusData(
            paper_id="status-restart",
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="classifying",
            updated_at=now,
        ),
    )

    service = await restart_paper_service()
    status = await service.get_status("status-restart")
    assert status.stage == PipelineStage.CLASSIFYING
    assert status.percent == 50
