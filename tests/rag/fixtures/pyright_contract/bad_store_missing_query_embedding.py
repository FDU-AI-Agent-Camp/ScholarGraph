# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Pyright should fail: compile-time guard catches missing query_embedding kwarg."""

from __future__ import annotations

from typing import cast

from backend.rag.models import RetrievedChunk, RetrievedEntity, RetrievedRelation
from backend.rag.protocols import VectorStoreProtocol


class BrokenStoreMissingQueryEmbedding:
    async def exists(self, paper_id: str) -> bool:
        _ = paper_id
        return False

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        _ = (query_text, paper_id, top_k)
        return []

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
    ) -> list[RetrievedEntity]:
        _ = (query_text, paper_id, top_k)
        return []

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
    ) -> list[RetrievedRelation]:
        _ = (query_text, paper_id, top_k)
        return []

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        _ = (paper_id, chunk_id)
        return None


_inspect_missing_kwarg: VectorStoreProtocol = cast(BrokenStoreMissingQueryEmbedding, None)
