"""Static async contracts for RAG vector retrieval (Pyright structural typing)."""

from __future__ import annotations

from typing import Protocol

from backend.rag.models import RetrievedChunk, RetrievedEntity, RetrievedRelation


class VectorStoreProtocol(Protocol):
    """Frozen retrieval contract consumed by ``HybridRetriever`` and QA services.

    All concrete stores (Chroma ``VectorStore``, ``StaticMockVectorStore``, test
    doubles) must keep these keyword-only signatures aligned so HyDE can pass
    ``query_embedding`` without runtime TypeError.
    """

    async def exists(self, paper_id: str) -> bool:
        """Return true when vector evidence is indexed for the paper."""
        ...

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        """Return chunk evidence scoped to one paper."""
        ...

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedEntity]:
        """Return entity evidence scoped to one paper."""
        ...

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedRelation]:
        """Return relation evidence scoped to one paper."""
        ...

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        """Return original chunk text for L2 citation preview lookup."""
        ...
