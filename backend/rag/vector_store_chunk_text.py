# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Per-instance LRU chunk text lookup for VectorStore (B10 L2 preview)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING

from backend.rag.models import VectorEvidenceType

if TYPE_CHECKING:
    from backend.rag.vector_store_utils import ChromaWhere, CollectionProtocol
    from backend.services.paper_service import PaperService


class ChunkTextLookupMixin:
    """Mixin: ``get_chunk_text`` with bounded LRU cache over Chroma documents."""

    _chunk_collection: CollectionProtocol
    _paper_service: PaperService | None
    _get_chunk_text_cached: Callable[[str, str, str], str]

    def _build_where(self, paper_id: str, *, run_id: str | None) -> ChromaWhere:
        """Implemented by ``VectorStore`` — filters by paper and optional run id."""
        raise NotImplementedError

    def _bind_chunk_text_lru(self) -> None:
        """Attach a per-instance ``functools.lru_cache`` for repeated L2 chunk lookups."""

        @lru_cache(maxsize=512)
        def _get_chunk_text_cached(paper_id: str, chunk_id: str, run_id: str) -> str:
            text = self._fetch_chunk_text_sync(paper_id, chunk_id, run_id or None)
            return text if text else ""

        self._get_chunk_text_cached = _get_chunk_text_cached

    def clear_chunk_text_lru(self) -> None:
        """Invalidate cached chunk text (e.g. after index replace/delete)."""
        self._get_chunk_text_cached.cache_clear()

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        """Fetch chunk document text by logical ``chunk_id`` (L2 citation preview lookup)."""
        if not paper_id or not chunk_id:
            return None

        run_id: str | None = None
        if self._paper_service is not None:
            run_id = self._paper_service.get_active_run_id(paper_id)
            # Fail-closed: no active run → ghosts stay invisible for L2 preview.
            if not run_id:
                return None

        cached = await asyncio.to_thread(
            self._get_chunk_text_cached,
            paper_id,
            chunk_id,
            run_id or "",
        )
        return cached if cached else None

    def _fetch_chunk_text_sync(self, paper_id: str, chunk_id: str, run_id: str | None) -> str | None:
        """Uncached Chroma read — wrapped by ``_get_chunk_text_cached``."""
        where: ChromaWhere = {
            "$and": [
                self._build_where(paper_id, run_id=run_id),
                {"chunk_id": chunk_id},
                {"evidence_type": VectorEvidenceType.CHUNK.value},
            ],
        }
        result = self._chunk_collection.get(where=where, limit=1, include=["documents"])
        documents = result.get("documents") if isinstance(result, dict) else None
        if not documents:
            return None
        first = documents[0]
        return first if isinstance(first, str) and first.strip() else None
