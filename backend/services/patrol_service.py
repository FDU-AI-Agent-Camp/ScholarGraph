"""Community patrol service facade (BE-4 implements backend.patrol)."""

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
                vector_store=self._vector_store,
                embedding_client=self._embedding_client,
            )
        except PatrolError as exc:
            raise ApiError(
                exc.code,
                exc.message,
                status_code=exc.status_code,
            ) from exc


@lru_cache
def get_patrol_service() -> PatrolService:
    from backend.rag.vector_store import VectorStore
    from backend.services.paper_service import get_paper_service

    return PatrolService(
        vector_store=VectorStore(paper_service=get_paper_service()),
        embedding_client=get_embedding_client(),
    )
