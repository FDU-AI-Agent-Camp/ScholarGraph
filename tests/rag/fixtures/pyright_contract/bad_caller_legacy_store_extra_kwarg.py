# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Pyright should fail: HybridRetriever-style call with query_embedding on legacy store."""

from __future__ import annotations

from backend.rag.models import RetrievedChunk


class LegacyStoreWithoutHydeKwarg:
    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        _ = (query_text, paper_id, top_k)
        return []


async def hybrid_retriever_style_call(
    store: LegacyStoreWithoutHydeKwarg,
    query_embedding: list[float] | None,
) -> None:
    await store.query_chunks(
        "ImageNet accuracy",
        paper_id="stem-001",
        top_k=2,
        query_embedding=query_embedding,
    )
