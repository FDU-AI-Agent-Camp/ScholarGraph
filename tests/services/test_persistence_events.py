"""Unit tests for PipelineFinalized event bus."""

from __future__ import annotations

import pytest
from backend.events.bus import EventBus
from backend.events.types import EventType, PipelineFinalized
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


@pytest.mark.asyncio
async def test_publish_pipeline_finalized_invokes_subscriber() -> None:
    bus = EventBus()
    seen: list[PipelineFinalized] = []

    async def handler(event: PipelineFinalized) -> None:
        seen.append(event)

    bus.subscribe(EventType.PIPELINE_FINALIZED, handler)
    graph = UnifiedPaperGraph(
        paper_id="evt-1",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="M", type="Method")],
        edges=[],
    )
    event = PipelineFinalized(paper_id="evt-1", full_text="body", graph=graph)
    await bus.publish(event)
    await bus.drain()
    assert len(seen) == 1
    assert seen[0].paper_id == "evt-1"
    assert seen[0].full_text == "body"


@pytest.mark.asyncio
async def test_handler_failure_does_not_break_bus(persistence_env) -> None:
    bus = EventBus()

    async def boom(_event: PipelineFinalized) -> None:
        raise RuntimeError("handler failed")

    bus.subscribe(EventType.PIPELINE_FINALIZED, boom)
    graph = UnifiedPaperGraph(
        paper_id="evt-2",
        paradigm=Paradigm.STEM,
        nodes=[],
        edges=[],
    )
    await bus.publish(PipelineFinalized(paper_id="evt-2", full_text="", graph=graph))
    await bus.drain()
