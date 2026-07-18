# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Finalize pipeline: validate graph payload, persist, mark paper ready."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from backend.agents.extract_constants import (
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    LOW_CONFIDENCE_GRAPH_CODE,
)
from backend.graph.quality_gate import evaluate_graph_quality
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import ParadigmClassification
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError
from backend.services.graph_persistence_service import (
    GraphPersistenceService,
    get_graph_persistence_service,
)

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)


async def complete_paper_pipeline(
    paper_service: PaperService,
    paper_id: str,
    *,
    classification: ParadigmClassification,
    graph: UnifiedPaperGraph,
    graph_path: str,
    extract_warnings: list[str] | None = None,
    full_text: str = "",
    page_break_offsets: list[int] | None = None,
    pipeline_generation_id: str | None = None,
) -> None:
    """Mark paper ready after graph has been persisted exactly once upstream.

    ``graph_path`` must come from :class:`GraphPersistenceService` (or an injected
    test double); this function does not write to ``GraphStore`` directly.

    ``pipeline_generation_id`` is the extract-run token captured at task start; it
    must still match ``pipeline_runs.pipeline_generation_id`` or terminal SQL is refused.
    """
    from backend.services.pipeline_generation_guard import assert_pipeline_generation_writable

    assert_pipeline_generation_writable(paper_id, pipeline_generation_id)
    await paper_service.require_paper_for_pipeline(paper_id)

    extract_warnings = list(extract_warnings or ())
    is_fallback = EXTRACT_HEURISTIC_FALLBACK_CODE in extract_warnings

    min_coverage, max_isolated, max_generic = paper_service.get_extract_quality_thresholds()
    if is_fallback:
        passed, reasons = True, []
    else:
        passed, reasons = evaluate_graph_quality(
            graph,
            min_supports_rationale_coverage=min_coverage,
            max_isolated_node_ratio=max_isolated,
            max_generic_edge_ratio=max_generic,
        )

    final_status = PaperStatus.READY if passed else PaperStatus.READY_WITH_WARNINGS
    warnings: list[str] = []
    if not passed:
        warnings.append(LOW_CONFIDENCE_GRAPH_CODE)

    await paper_service.update_pipeline_classification(paper_id, classification)

    config_hash = paper_service.compute_extractor_config_hash()
    await paper_service.update_pipeline_graph_path(paper_id, graph_path=graph_path)
    graph_version = await paper_service.get_pipeline_graph_version(paper_id)
    await paper_service.update_pipeline_graph_version(
        paper_id,
        graph_version=graph_version,
        extractor_config_hash=config_hash,
    )
    merged_extract_warnings = list(extract_warnings or ())
    if warnings:
        merged_extract_warnings = list(dict.fromkeys([*merged_extract_warnings, *warnings]))
    # P10 state gate: do not advertise READY until RAG index completes.
    # Use async persist — sync mark_indexing → run_async deadlocks the EventBus worker.
    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PipelineStage
    from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
    from backend.services.paper_status_transitions import assert_status_transition_allowed
    from backend.services.pipeline_status_service import DEFAULT_STAGE_MESSAGES
    from backend.services.status_snapshot_guard import apersist_status_snapshot

    existing = await get_paper_pipeline_ops_service().get_pipeline_snapshot(paper_id)
    if existing is not None:
        assert_status_transition_allowed(existing.status, PaperStatus.INDEXING, paper_id=paper_id)
    await apersist_status_snapshot(
        paper_service,
        paper_id,
        status=PaperStatus.INDEXING,
        stage=PipelineStage.INDEXING,
        percent=STAGE_PERCENT[PipelineStage.INDEXING],
        message=DEFAULT_STAGE_MESSAGES[PipelineStage.INDEXING],
        append_extract_warnings=merged_extract_warnings or None,
    )

    from backend.events.bus import get_event_bus
    from backend.events.pipeline_finalized_contract import pipeline_finalized_correlation_id
    from backend.events.types import PipelineFinalized

    correlation_id = pipeline_finalized_correlation_id(paper_id)
    logger.info(
        "pipeline_db_committed",
        extra={
            "correlation_id": correlation_id,
            "paper_id": paper_id,
            "status": PaperStatus.INDEXING.value,
            "terminal_status": final_status.value,
            "channel": "persistence_db",
        },
    )

    finalized_event = PipelineFinalized(
        paper_id=paper_id,
        full_text=full_text,
        graph=graph,
        page_break_offsets=page_break_offsets,
        terminal_status=final_status,
        warning_message="; ".join(reasons) if reasons else None,
    )
    logger.info(
        "pipeline_finalized_publishing",
        extra={
            "correlation_id": correlation_id,
            "paper_id": paper_id,
            "event_type": finalized_event.event_type.value,
            "channel": "event_bus_publisher",
            "full_text_chars": len(full_text),
            "graph_node_count": len(graph.nodes),
            "graph_edge_count": len(graph.edges),
        },
    )
    await get_event_bus().publish(finalized_event)
    await paper_service.clear_preview_graph(paper_id)


class PipelineCompletionService:
    """Store step orchestration (validation + persistence + paper status)."""

    def __init__(self, graph_persistence: GraphPersistenceService | None = None) -> None:
        self._graph_persistence = graph_persistence

    async def finalize(
        self,
        paper_id: str,
        *,
        graph_data: dict[str, Any],
        classification_data: dict[str, Any],
        extract_warnings: list[str] | None = None,
        full_text: str = "",
        page_break_offsets: list[int] | None = None,
        pipeline_generation_id: str | None = None,
    ) -> UnifiedPaperGraph:
        try:
            from backend.services.pipeline_generation_guard import assert_pipeline_generation_writable

            # Gate BEFORE GraphStore write so orphans cannot dirty disk after kill.
            assert_pipeline_generation_writable(paper_id, pipeline_generation_id)
            graph = UnifiedPaperGraph.model_validate(graph_data)
            classification = ParadigmClassification.model_validate(classification_data)
            persistence = self._graph_persistence or get_graph_persistence_service()
            graph_path = await persistence.save(graph)
            from backend.services.paper_service import get_paper_service

            await complete_paper_pipeline(
                get_paper_service(),
                paper_id,
                classification=classification,
                graph=graph,
                graph_path=graph_path,
                extract_warnings=extract_warnings,
                full_text=full_text,
                page_break_offsets=page_break_offsets,
                pipeline_generation_id=pipeline_generation_id,
            )
            return graph
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, f"建图收尾失败: {exc}") from exc


@lru_cache
def get_pipeline_completion_service() -> PipelineCompletionService:
    return PipelineCompletionService()
