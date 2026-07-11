"""PatrolService facade with mode-aware lazy RAG/embedding dependencies."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from backend.api.exceptions import ApiError
from backend.graph.store import GraphStore
from backend.llm.embeddings import EmbeddingClient, get_embedding_client
from backend.patrol.errors import PatrolError
from backend.patrol.service import run_patrol as patrol_run
from backend.schemas.patrol import PatrolMode, PatrolReport

if TYPE_CHECKING:
    from backend.rag.vector_store import VectorStore

_PATROL_RAG_MODES = frozenset(
    {
        PatrolMode.METHOD_OVERLAP,
        PatrolMode.CLAIM_EVOLUTION,
        PatrolMode.CONTRADICTION,
    }
)
_PATROL_EMBEDDING_MODES = frozenset(
    {
        PatrolMode.METHOD_OVERLAP,
        PatrolMode.CLAIM_EVOLUTION,
    }
)


class PatrolService:
    """Delegates patrol execution to BE-4 ``run_patrol`` (handoff §5 / collaboration §4.4)."""

    def __init__(
        self,
        store: GraphStore | None = None,
        *,
        vector_store: VectorStore | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._store = store
        self._vector_store = vector_store
        self._embedding_client = embedding_client
        self._lazy_vector_store: VectorStore | None = None
        self._lazy_embedding_client: EmbeddingClient | None = None

    async def run_patrol(
        self,
        paper_ids: list[str],
        mode: PatrolMode = PatrolMode.LENS_CLASH,
    ) -> PatrolReport:
        try:
            return await patrol_run(
                paper_ids,
                mode,
                store=self._store,
                vector_store=self._resolve_vector_store(mode),
                embedding_client=self._resolve_embedding_client(mode),
            )
        except PatrolError as exc:
            raise ApiError(
                exc.code,
                exc.message,
                status_code=exc.status_code,
            ) from exc

    def _resolve_vector_store(self, mode: PatrolMode) -> VectorStore | None:
        if mode not in _PATROL_RAG_MODES:
            return None
        if self._vector_store is not None:
            return self._vector_store
        if self._lazy_vector_store is None:
            from backend.rag.vector_store import VectorStore
            from backend.services.paper_service import get_paper_service

            self._lazy_vector_store = VectorStore(paper_service=get_paper_service())
        return self._lazy_vector_store

    def _resolve_embedding_client(self, mode: PatrolMode) -> EmbeddingClient | None:
        if mode not in _PATROL_EMBEDDING_MODES:
            return None
        if self._embedding_client is not None:
            return self._embedding_client
        if self._lazy_embedding_client is None:
            self._lazy_embedding_client = get_embedding_client()
        return self._lazy_embedding_client


@lru_cache
def get_patrol_service() -> PatrolService:
    return PatrolService()
