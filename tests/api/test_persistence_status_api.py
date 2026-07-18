# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""API status contract tests with DB backend (API-STATUS-01/02)."""

from __future__ import annotations

import pytest
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.pipeline_completion_service import PipelineCompletionService
from httpx import AsyncClient
from tests.api.conftest import assert_success_envelope
from tests.helpers.event_bus_testkit import drain_event_bus
from tests.helpers.persistence_testkit import mock_graph_persistence
from tests.helpers.status_contract import assert_snapshot_matches_contract

VALID_PDF = b"%PDF-1.4\n% status api test"


@pytest.mark.asyncio
async def test_status_pending_after_upload_matches_contract(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("status.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    from backend.schemas.paper import PaperStatusData

    snapshot = PaperStatusData.model_validate(body["data"])
    assert snapshot.status == PaperStatus.PENDING
    assert snapshot.percent == 0
    assert snapshot.stage is None
    assert_snapshot_matches_contract(snapshot)


@pytest.mark.asyncio
async def test_status_ready_after_finalize_matches_contract(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("ready.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]

    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="api")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="T", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    persistence = mock_graph_persistence(paper_id, graph_dir=persistence_env["graph_dir"])
    await PipelineCompletionService(graph_persistence=persistence).finalize(
        paper_id,
        graph_data=graph.model_dump(mode="json"),
        classification_data=classification.model_dump(mode="json"),
        full_text="status api finalize body",
    )
    await drain_event_bus()

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == PaperStatus.READY.value
    assert data["stage"] == PipelineStage.READY.value
    assert data["percent"] == 100
