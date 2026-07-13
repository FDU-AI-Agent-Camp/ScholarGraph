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
from backend.repositories.async_bridge import run_async
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


def complete_paper_pipeline(
    paper_service: PaperService,
    paper_id: str,
    *,
    classification: ParadigmClassification,
    graph: UnifiedPaperGraph,
    extract_warnings: list[str] | None = None,
    full_text: str = "",
    page_break_offsets: list[int] | None = None,
) -> None:
    """Persist graph and mark paper ready or ready_with_warnings.

    The quality gate is skipped when the graph came from a heuristic fallback,
    because fallback graphs are intentionally degraded and should not be
    double-penalized.
    """
    paper_service.require_paper_for_pipeline(paper_id)

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

    paper_service.update_pipeline_classification(paper_id, classification)
    from backend.graph.store import GraphStore
    from backend.services.pipeline_status_service import get_pipeline_status_service

    graph_store = GraphStore()
    graph_store.save(graph)
    graph_path = str(graph_store._path(paper_id))
    config_hash = paper_service.compute_extractor_config_hash()
    paper_service.update_pipeline_graph_path(paper_id, graph_path=graph_path)
    graph_version = paper_service.get_pipeline_graph_version(paper_id)
    paper_service.update_pipeline_graph_version(
        paper_id,
        graph_version=graph_version,
        extractor_config_hash=config_hash,
    )
    if warnings:
        paper_service.record_extract_warnings(paper_id, warnings)

    status_service = get_pipeline_status_service()
    if final_status == PaperStatus.READY:
        status_service.mark_ready(paper_id)
    else:
        status_service.mark_ready_with_warnings(paper_id, message="; ".join(reasons))

    from backend.events.bus import get_event_bus
    from backend.events.pipeline_finalized_contract import pipeline_finalized_correlation_id
    from backend.events.types import PipelineFinalized

    correlation_id = pipeline_finalized_correlation_id(paper_id)
    logger.info(
        "pipeline_db_committed",
        extra={
            "correlation_id": correlation_id,
            "paper_id": paper_id,
            "status": final_status.value,
            "channel": "persistence_db",
        },
    )

    finalized_event = PipelineFinalized(
        paper_id=paper_id,
        full_text=full_text,
        graph=graph,
        page_break_offsets=page_break_offsets,
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
    get_event_bus().publish_sync(finalized_event)
    run_async(paper_service._pipeline_repo.clear_preview_graph(paper_id))


class PipelineCompletionService:
    """Store step orchestration (validation + persistence + paper status)."""

    def __init__(self, graph_persistence: GraphPersistenceService | None = None) -> None:
        self._graph_persistence = graph_persistence

    def finalize(
        self,
        paper_id: str,
        *,
        graph_data: dict[str, Any],
        classification_data: dict[str, Any],
        extract_warnings: list[str] | None = None,
        full_text: str = "",
        page_break_offsets: list[int] | None = None,
    ) -> UnifiedPaperGraph:
        try:
            graph = UnifiedPaperGraph.model_validate(graph_data)
            classification = ParadigmClassification.model_validate(classification_data)
            persistence = self._graph_persistence or get_graph_persistence_service()
            persistence.save(graph)
            from backend.services.paper_service import get_paper_service

            complete_paper_pipeline(
                get_paper_service(),
                paper_id,
                classification=classification,
                graph=graph,
                extract_warnings=extract_warnings,
                full_text=full_text,
                page_break_offsets=page_break_offsets,
            )
            return graph
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, f"建图收尾失败: {exc}") from exc


@lru_cache
def get_pipeline_completion_service() -> PipelineCompletionService:
    return PipelineCompletionService()
