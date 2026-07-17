# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Graph persistence facade (BE-3 implements backend.graph.store)."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from backend.schemas.graph import UnifiedPaperGraph
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError

if TYPE_CHECKING:
    from backend.graph.store import GraphStore


def __getattr__(name: str) -> object:
    """Lazily re-export GraphStore so existing patches keep working."""
    if name == "GraphStore":
        from backend.graph.store import GraphStore

        return GraphStore
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


class GraphPersistenceService:
    """Persist UnifiedPaperGraph to configured storage."""

    def __init__(self, store: GraphStore | None = None) -> None:
        from backend.graph.store import GraphStore

        self._store = store or GraphStore()

    def save(self, graph: UnifiedPaperGraph) -> str:
        """Persist graph and return the resolved on-disk path."""
        try:
            self._store.save(graph)
            return str(self._store._path(graph.paper_id))
        except Exception as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, f"图谱存储失败: {exc}") from exc


@lru_cache
def get_graph_persistence_service() -> GraphPersistenceService:
    return GraphPersistenceService()
