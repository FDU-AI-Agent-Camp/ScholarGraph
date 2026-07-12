"""Integration test: finalize emits PipelineFinalized (INT-EVT-01, EVT-03)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from backend.events.bus import EventBus
from backend.events.types import EventType, PipelineFinalized
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.pipeline_completion_service import PipelineCompletionService

from tests.helpers.persistence_testkit import register_test_paper


@pytest.mark.integration
@pytest.mark.asyncio
async def test_finalize_publishes_pipeline_finalized_event(persistence_env) -> None:
    paper_id = "evt-finalize-001"
    await register_test_paper(paper_id, title="event paper")

    bus = EventBus()
    seen: list[PipelineFinalized] = []

    async def capture(event: PipelineFinalized) -> None:
        seen.append(event)

    bus.subscribe(EventType.PIPELINE_FINALIZED, capture)

    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="evt")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="T", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    persistence = MagicMock(spec=GraphPersistenceService)
    completion = PipelineCompletionService(graph_persistence=persistence)

    from backend.events import bus as bus_module
    from backend.services import pipeline_completion_service as pcs_module

    original_get = bus_module.get_event_bus
    bus_module.get_event_bus = lambda: bus  # type: ignore[assignment]
    pcs_module.get_event_bus = lambda: bus  # type: ignore[attr-defined]
    try:
        completion.finalize(
            paper_id,
            graph_data=graph.model_dump(mode="json"),
            classification_data=classification.model_dump(mode="json"),
        )
        await bus.drain()
    finally:
        bus_module.get_event_bus = original_get

    assert len(seen) == 1
    assert seen[0].paper_id == paper_id
    assert seen[0].graph.paper_id == paper_id
