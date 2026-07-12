"""API graph endpoint tests with DB backend (API-GRAPH-01/02)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.pipeline_completion_service import PipelineCompletionService
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope

VALID_PDF = b"%PDF-1.4\n% graph api test"


@pytest.mark.asyncio
async def test_graph_pending_paper_returns_409(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("pending.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]

    response = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert response.status_code == 409
    assert_error_envelope(response.json(), code="GRAPH_NOT_READY")


@pytest.mark.asyncio
async def test_graph_ready_paper_returns_unified_graph(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("graph-ready.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]

    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="graph")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="T", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    persistence = MagicMock(spec=GraphPersistenceService)
    PipelineCompletionService(graph_persistence=persistence).finalize(
        paper_id,
        graph_data=graph.model_dump(mode="json"),
        classification_data=classification.model_dump(mode="json"),
    )

    response = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert response.status_code == 200
    assert_success_envelope(response.json())
    assert response.json()["data"]["paper_id"] == paper_id
