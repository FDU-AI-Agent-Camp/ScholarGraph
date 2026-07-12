"""Pyright should fail: compile-time guard catches wrong query_chunks return type."""

from __future__ import annotations

from typing import cast

from backend.rag.models import RetrievedEntity, RetrievedRelation
from backend.rag.protocols import VectorStoreProtocol


class WrongReturnTypeStore:
    async def exists(self, paper_id: str) -> bool:
        _ = paper_id
        return False

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[str]:
        _ = (query_text, paper_id, top_k, query_embedding)
        return []

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedEntity]:
        _ = (query_text, paper_id, top_k, query_embedding)
        return []

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedRelation]:
        _ = (query_text, paper_id, top_k, query_embedding)
        return []

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        _ = (paper_id, chunk_id)
        return None


_inspect_wrong_return: VectorStoreProtocol = cast(WrongReturnTypeStore, None)
