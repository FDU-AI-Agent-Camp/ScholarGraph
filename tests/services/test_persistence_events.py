"""Unit tests for PipelineFinalized event bus."""

from __future__ import annotations

import asyncio

import pytest
from backend.events.bus import EventBus
from backend.events.types import EventType, PipelineFinalized
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


@pytest.mark.asyncio
async def test_publish_sync_is_fire_and_forget_until_explicit_drain() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def handler(event: PipelineFinalized) -> None:
        await asyncio.sleep(0.05)
        seen.append(event.paper_id)

    bus.subscribe(EventType.PIPELINE_FINALIZED, handler)
    graph = UnifiedPaperGraph(
        paper_id="ff-1",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="M", type="Method")],
        edges=[],
    )

    async def trigger_publish_sync() -> None:
        bus.publish_sync(PipelineFinalized(paper_id="ff-1", full_text="body", graph=graph))

    await asyncio.to_thread(lambda: bus.publish_sync(PipelineFinalized(paper_id="ff-1", full_text="body", graph=graph)))
    assert seen == []

    await asyncio.to_thread(bus.drain_sync)
    assert seen == ["ff-1"]


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
async def test_handler_failure_records_extract_warning_via_error_hook(persistence_env) -> None:
    from backend.events.handler_errors import EVENT_HANDLER_FAILED_CODE, persist_event_handler_failure
    from backend.services.paper_service import get_paper_service
    from tests.helpers.persistence_testkit import register_test_paper

    paper_id = "evt-hook-1"
    await register_test_paper(paper_id)
    bus = EventBus(on_handler_error=persist_event_handler_failure)

    async def boom(_event: PipelineFinalized) -> None:
        raise RuntimeError("handler failed")

    bus.subscribe(EventType.PIPELINE_FINALIZED, boom)
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="M", type="Method")],
        edges=[],
    )
    await bus.publish(PipelineFinalized(paper_id=paper_id, full_text="body", graph=graph))
    await bus.drain()

    snapshot = await get_paper_service().get_status(paper_id)
    assert any(EVENT_HANDLER_FAILED_CODE in w for w in snapshot.extract_warnings)
    assert any("handler failed" in w for w in snapshot.extract_warnings)


@pytest.mark.asyncio
async def test_malicious_handler_crash_persists_summary_to_pipeline_runs(persistence_env) -> None:
    """D12 smoke: bus error hook must append handler exception summary to pipeline_runs."""
    from backend.db.base import get_async_session_factory
    from backend.db.models import PipelineRunRow
    from backend.events.handler_errors import persist_event_handler_failure
    from tests.helpers.persistence_testkit import register_test_paper

    paper_id = "evt-rag-disk-full"
    await register_test_paper(paper_id)
    bus = EventBus(on_handler_error=persist_event_handler_failure)

    async def malicious_rag_handler(_event: PipelineFinalized) -> None:
        raise RuntimeError("RAG disk full")

    bus.subscribe(EventType.PIPELINE_FINALIZED, malicious_rag_handler)
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="M", type="Method")],
        edges=[],
    )
    await bus.publish(PipelineFinalized(paper_id=paper_id, full_text="body", graph=graph))
    await bus.drain()

    async with get_async_session_factory()() as session:
        run = await session.get(PipelineRunRow, paper_id)
        assert run is not None
        extract_warnings = list(run.extract_warnings or [])

    assert any("RAG disk full" in warning for warning in extract_warnings)


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


@pytest.mark.asyncio
async def test_temporary_pipeline_finalized_handler_delegates_to_rag_index_service(
    persistence_env,
) -> None:
    from unittest.mock import AsyncMock, patch

    from backend.events.pipeline_finalized_handlers import temporary_pipeline_finalized_rag_handler
    from tests.helpers.persistence_testkit import register_test_paper

    paper_id = "evt-rag-1"
    await register_test_paper(paper_id)
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="M", type="Method")],
        edges=[],
    )
    event = PipelineFinalized(paper_id=paper_id, full_text="full body", graph=graph)

    with patch(
        "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
        new_callable=AsyncMock,
    ) as mock_index:
        await temporary_pipeline_finalized_rag_handler(event)

    mock_index.assert_awaited_once_with(
        paper_id,
        full_text="full body",
        graph=graph,
        page_break_offsets=None,
    )
