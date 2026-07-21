# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""PatrolService facade with mode-aware lazy RAG/embedding dependencies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from functools import lru_cache
from typing import TYPE_CHECKING

from backend.api.exceptions import ApiError
from backend.graph.store import GraphStore
from backend.llm.embeddings import EmbeddingClient, get_embedding_client
from backend.patrol.degradation import report_has_rag_degradation
from backend.patrol.errors import PatrolError
from backend.patrol.result_cache import (
    InMemoryPatrolResultCache,
    PatrolResultCacheProtocol,
    build_patrol_cache_key,
    collect_patrol_paper_fingerprint,
)
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

PaperFingerprintFn = Callable[[Sequence[str]], Awaitable[str]]


class PatrolService:
    """Delegates patrol execution to BE-4 ``run_patrol`` (handoff §5 / collaboration §4.4)."""

    def __init__(
        self,
        store: GraphStore | None = None,
        *,
        vector_store: VectorStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        result_cache: PatrolResultCacheProtocol | None = None,
        cache_enabled: bool = True,
        paper_fingerprint_fn: PaperFingerprintFn | None = None,
    ) -> None:
        self._store = store
        self._vector_store = vector_store
        self._embedding_client = embedding_client
        self._lazy_vector_store: VectorStore | None = None
        self._lazy_embedding_client: EmbeddingClient | None = None
        self._cache: PatrolResultCacheProtocol | None = (
            result_cache if result_cache is not None else InMemoryPatrolResultCache()
        )
        self._cache_enabled = cache_enabled
        self._paper_fingerprint_fn = paper_fingerprint_fn or collect_patrol_paper_fingerprint

    async def run_patrol(
        self,
        paper_ids: list[str],
        mode: PatrolMode = PatrolMode.LENS_CLASH,
    ) -> PatrolReport:
        fingerprint = ""
        if self._cache_enabled:
            fingerprint = await self._paper_fingerprint_fn(paper_ids)
        cache_key = build_patrol_cache_key(paper_ids, mode, paper_fingerprint=fingerprint)
        if self._cache_enabled and self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            report = await patrol_run(
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

        # Never cache degraded (thin RAG) reports — FE heal polls at 10s/30s/60s must
        # re-run analyzers once the index lands, not reuse a stale thin entry (P9).
        if self._cache_enabled and self._cache is not None and not report_has_rag_degradation(report):
            self._cache.set(cache_key, report)
        return report

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
