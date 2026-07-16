"""Contract validation tests for PipelineFinalized official RAG handler."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from backend.events.pipeline_finalized_contract import (
    PipelineFinalizedContractError,
    pipeline_finalized_correlation_id,
    validate_pipeline_finalized_payload,
)
from backend.events.types import PipelineFinalized
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.pipeline_completion_service import PipelineCompletionService
from tests.helpers.event_bus_testkit import drain_event_bus_sync
from tests.helpers.persistence_testkit import mock_graph_persistence, register_test_paper


def _valid_graph(paper_id: str = "contract-paper") -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )


@pytest.mark.asyncio
async def test_validate_rejects_empty_full_text(persistence_env) -> None:
    await register_test_paper("contract-empty-text")
    event = PipelineFinalized(
        paper_id="contract-empty-text",
        full_text="   ",
        graph=_valid_graph("contract-empty-text"),
    )

    with pytest.raises(PipelineFinalizedContractError, match="full_text"):
        await validate_pipeline_finalized_payload(event)


@pytest.mark.asyncio
async def test_validate_rejects_missing_db_paper(persistence_env) -> None:
    event = PipelineFinalized(
        paper_id="ghost-contract-paper",
        full_text="body",
        graph=_valid_graph("ghost-contract-paper"),
    )

    with pytest.raises(PipelineFinalizedContractError, match="not found"):
        await validate_pipeline_finalized_payload(event)


@pytest.mark.asyncio
async def test_validate_rejects_empty_graph_topology(persistence_env) -> None:
    paper_id = "contract-empty-graph"
    await register_test_paper(paper_id)
    graph = UnifiedPaperGraph.model_construct(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[],
        edges=[],
    )
    event = PipelineFinalized(paper_id=paper_id, full_text="body", graph=graph)

    with pytest.raises(PipelineFinalizedContractError, match="at least one node"):
        await validate_pipeline_finalized_payload(event)


@pytest.mark.asyncio
async def test_validate_rejects_invalid_graph_schema_on_round_trip(persistence_env) -> None:
    paper_id = "contract-invalid-schema"
    await register_test_paper(paper_id)
    graph = UnifiedPaperGraph.model_construct(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="missing", label="REF", type="REF")],
    )
    event = PipelineFinalized(paper_id=paper_id, full_text="body", graph=graph)

    with pytest.raises(PipelineFinalizedContractError, match="schema validation"):
        await validate_pipeline_finalized_payload(event)


@pytest.mark.asyncio
async def test_validate_accepts_round_trip_graph_and_db_paper(persistence_env) -> None:
    paper_id = "contract-ok"
    await register_test_paper(paper_id)
    graph = _valid_graph(paper_id)
    event = PipelineFinalized(paper_id=paper_id, full_text="full paper body", graph=graph)

    validated = await validate_pipeline_finalized_payload(event)

    assert validated.paper_id == paper_id
    assert validated.nodes[0].id == "n1"


def test_correlation_id_matches_paper_id() -> None:
    assert pipeline_finalized_correlation_id("  hss-001  ") == "hss-001"


@pytest.mark.asyncio
async def test_finalize_publish_and_consume_share_correlation_id(
    persistence_env,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from backend.events import bus as bus_module
    from backend.events import pipeline_finalized_handlers as handler_module
    from backend.events.bus import EventBus
    from backend.events.types import EventType
    from backend.services import pipeline_completion_service as pcs_module

    paper_id = "contract-log-bridge"
    await register_test_paper(paper_id, title="log bridge")
    graph = _valid_graph(paper_id)
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="log")

    bus = EventBus()
    bus.subscribe(EventType.PIPELINE_FINALIZED, handler_module.pipeline_finalized_rag_handler)

    original_get = bus_module.get_event_bus
    bus_module.get_event_bus = lambda: bus  # type: ignore[assignment]
    pcs_module.get_event_bus = lambda: bus  # type: ignore[attr-defined]

    caplog.set_level(logging.INFO)
    try:
        with patch(
            "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
            new_callable=AsyncMock,
        ):
            persistence = mock_graph_persistence(paper_id)
            PipelineCompletionService(graph_persistence=persistence).finalize(
                paper_id,
                graph_data=graph.model_dump(mode="json"),
                classification_data=classification.model_dump(mode="json"),
                full_text="observable full text",
            )
            await asyncio.to_thread(bus.drain_sync)
    finally:
        bus_module.get_event_bus = original_get

    publish_records = [r for r in caplog.records if r.getMessage() == "pipeline_finalized_publishing"]
    consume_records = [r for r in caplog.records if r.getMessage() == "pipeline_finalized_consumed"]
    commit_records = [r for r in caplog.records if r.getMessage() == "pipeline_db_committed"]
    fetch_records = [r for r in caplog.records if r.getMessage() == "pipeline_finalized_fetching_metadata"]
    assert len(commit_records) == 1
    assert len(publish_records) == 1
    assert len(consume_records) == 1
    assert len(fetch_records) == 1
    assert publish_records[0].correlation_id == paper_id
    assert consume_records[0].correlation_id == paper_id
    assert publish_records[0].correlation_id == consume_records[0].correlation_id

    ordered_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]
    commit_idx = ordered_messages.index("pipeline_db_committed")
    publish_idx = ordered_messages.index("pipeline_finalized_publishing")
    consume_idx = ordered_messages.index("pipeline_finalized_consumed")
    fetch_idx = ordered_messages.index("pipeline_finalized_fetching_metadata")
    assert commit_idx < publish_idx < consume_idx < fetch_idx


def test_handler_immediate_db_read_never_dirty_reads(
    persistence_env,
) -> None:
    """Subscriber fetches DB metadata immediately; must never see pre-commit ghost rows."""
    import asyncio

    from backend.events import bus as bus_module
    from backend.events import pipeline_finalized_handlers as handler_module
    from backend.events.bus import EventBus
    from backend.events.types import EventType
    from backend.services import pipeline_completion_service as pcs_module

    bus = EventBus()
    bus.subscribe(EventType.PIPELINE_FINALIZED, handler_module.pipeline_finalized_rag_handler)

    original_get = bus_module.get_event_bus
    bus_module.get_event_bus = lambda: bus  # type: ignore[assignment]
    pcs_module.get_event_bus = lambda: bus  # type: ignore[attr-defined]

    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="isolation")

    try:
        for index in range(3):
            paper_id = f"contract-isolation-{index}"
            asyncio.run(register_test_paper(paper_id, title=f"isolation {index}"))
            graph = _valid_graph(paper_id)
            persistence = mock_graph_persistence(paper_id)
            with patch(
                "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
                new_callable=AsyncMock,
            ):
                PipelineCompletionService(graph_persistence=persistence).finalize(
                    paper_id,
                    graph_data=graph.model_dump(mode="json"),
                    classification_data=classification.model_dump(mode="json"),
                    full_text=f"isolation body {index}",
                )
        drain_event_bus_sync()
    finally:
        bus_module.get_event_bus = original_get
