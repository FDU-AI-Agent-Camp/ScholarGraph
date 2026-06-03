"""Graph persistence facade (BE-3 implements backend.graph.store)."""

from functools import lru_cache

from backend.graph.store import GraphStore
from backend.schemas.graph import UnifiedPaperGraph
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError


class GraphPersistenceService:
    """Persist UnifiedPaperGraph to configured storage."""

    def __init__(self, store: GraphStore | None = None) -> None:
        self._store = store or GraphStore()

    def save(self, graph: UnifiedPaperGraph) -> None:
        try:
            self._store.save(graph)
        except Exception as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, f"图谱存储失败: {exc}") from exc


@lru_cache
def get_graph_persistence_service() -> GraphPersistenceService:
    return GraphPersistenceService()
