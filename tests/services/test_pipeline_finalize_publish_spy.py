# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Spy tests: finalize() publishes PipelineFinalized exactly once with contract payload."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from backend.events.bus import EventBus
from backend.events.types import EventType, PipelineFinalized
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import ParadigmClassification
from backend.services.pipeline_completion_service import PipelineCompletionService
from tests.helpers.persistence_testkit import mock_graph_persistence


def test_finalize_publishes_pipeline_finalized_once_with_contract_payload(
    persistence_env,
    registered_paper: str,
    sample_graph: UnifiedPaperGraph,
    sample_classification: ParadigmClassification,
) -> None:
    from backend.events import bus as bus_module
    from backend.events import pipeline_finalized_handlers as handler_module
    from backend.services import pipeline_completion_service as pcs_module

    paper_id = registered_paper
    graph = sample_graph.model_copy(update={"paper_id": paper_id})
    full_text = "spy-test full paper body for RAG indexing"

    bus = EventBus()
    bus.subscribe(EventType.PIPELINE_FINALIZED, handler_module.pipeline_finalized_rag_handler)

    original_get = bus_module.get_event_bus
    bus_module.get_event_bus = lambda: bus  # type: ignore[assignment]
    pcs_module.get_event_bus = lambda: bus  # type: ignore[attr-defined]

    persistence = mock_graph_persistence(paper_id)
    service = PipelineCompletionService(graph_persistence=persistence)

    try:
        with (
            patch.object(bus, "publish_sync", wraps=bus.publish_sync) as publish_spy,
            patch(
                "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
                new_callable=AsyncMock,
            ),
        ):
            service.finalize(
                paper_id,
                graph_data=graph.model_dump(mode="json"),
                classification_data=sample_classification.model_dump(mode="json"),
                full_text=full_text,
                page_break_offsets=[10, 20],
            )

        publish_spy.assert_called_once()
        published_event = publish_spy.call_args[0][0]
        assert isinstance(published_event, PipelineFinalized)
        assert published_event.paper_id == paper_id
        assert published_event.full_text == full_text
        assert published_event.graph.paper_id == paper_id
        assert published_event.page_break_offsets == [10, 20]
        assert published_event.event_type == EventType.PIPELINE_FINALIZED
        assert len(published_event.graph.nodes) >= 1
    finally:
        bus_module.get_event_bus = original_get
