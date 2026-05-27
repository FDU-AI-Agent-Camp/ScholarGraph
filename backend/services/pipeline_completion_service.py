"""Finalize pipeline: validate graph payload, persist, mark paper ready."""

from functools import lru_cache
from typing import Any

from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import ParadigmClassification
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError
from backend.services.graph_persistence_service import (
    GraphPersistenceService,
    get_graph_persistence_service,
)
from backend.services.paper_service import get_paper_service


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
    ) -> UnifiedPaperGraph:
        try:
            graph = UnifiedPaperGraph.model_validate(graph_data)
            classification = ParadigmClassification.model_validate(classification_data)
            persistence = self._graph_persistence or get_graph_persistence_service()
            persistence.save(graph)
            get_paper_service().complete_pipeline(
                paper_id,
                classification=classification,
                graph=graph,
            )
            return graph
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, f"建图收尾失败: {exc}") from exc


@lru_cache
def get_pipeline_completion_service() -> PipelineCompletionService:
    return PipelineCompletionService()
