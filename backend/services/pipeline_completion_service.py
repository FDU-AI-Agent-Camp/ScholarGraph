"""Finalize pipeline: validate graph payload, persist, mark paper ready."""

from __future__ import annotations

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


def complete_paper_pipeline(
    paper_service: PaperService,
    paper_id: str,
    *,
    classification: ParadigmClassification,
    graph: UnifiedPaperGraph,
    extract_warnings: list[str] | None = None,
    full_text: str = "",
) -> None:
    """Persist graph and mark paper ready or ready_with_warnings.

    The quality gate is skipped when the graph came from a heuristic fallback,
    because fallback graphs are intentionally degraded and should not be
    double-penalized.
    """
    paper_service.ensure_paper_exists(paper_id)
    settings = paper_service._settings
    from backend.repositories import run_async
    from backend.services.extractor_config_fingerprint import compute_extractor_config_hash

    paper = run_async(paper_service._paper_repo.get(paper_id))
    if paper is None:
        msg = f"paper not found: {paper_id}"
        raise ServiceError(PIPELINE_FAILED_CODE, msg)

    extract_warnings = list(extract_warnings or ())
    is_fallback = EXTRACT_HEURISTIC_FALLBACK_CODE in extract_warnings

    if is_fallback:
        passed, reasons = True, []
    else:
        passed, reasons = evaluate_graph_quality(
            graph,
            min_supports_rationale_coverage=settings.extract_min_supports_rationale_coverage,
            max_isolated_node_ratio=settings.extract_max_isolated_node_ratio,
            max_generic_edge_ratio=settings.extract_max_generic_edge_ratio,
        )

    final_status = PaperStatus.READY if passed else PaperStatus.READY_WITH_WARNINGS
    warnings: list[str] = []
    if not passed:
        warnings.append(LOW_CONFIDENCE_GRAPH_CODE)

    run_async(
        paper_service._paper_repo.update_classification(paper_id, classification),
    )
    from backend.graph.store import GraphStore
    from backend.services.pipeline_status_service import get_pipeline_status_service

    graph_store = GraphStore()
    graph_store.save(graph)
    graph_path = str(graph_store._path(paper_id))
    config_hash = compute_extractor_config_hash(settings)
    run_async(
        paper_service._paper_repo.update_paths(paper_id, graph_path=graph_path),
    )
    run_async(
        paper_service._paper_repo.update_graph_version(
            paper_id,
            graph_version="1",
            extractor_config_hash=config_hash,
        ),
    )
    if warnings:
        paper_service.record_extract_warnings(paper_id, warnings)

    status_service = get_pipeline_status_service()
    if final_status == PaperStatus.READY:
        status_service.mark_ready(paper_id)
    else:
        status_service.mark_ready_with_warnings(paper_id, message="; ".join(reasons))

    from backend.events.bus import get_event_bus
    from backend.events.types import PipelineFinalized

    get_event_bus().publish_sync(
        PipelineFinalized(paper_id=paper_id, full_text=full_text, graph=graph),
    )


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
            )
            return graph
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, f"建图收尾失败: {exc}") from exc


@lru_cache
def get_pipeline_completion_service() -> PipelineCompletionService:
    return PipelineCompletionService()
