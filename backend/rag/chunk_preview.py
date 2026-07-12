"""Chunk citation ``text_preview`` resolution — L1 cache + L2 vector lookup (B10)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from backend.schemas.chunk_preview import (
    ChunkPreviewState,
    ResolvedChunkPreview,
    truncate_chunk_preview,
)
from backend.services.qa_retrieval import VECTOR_RETRIEVAL_TIMEOUT_CODE

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

L2_CHUNK_LOOKUP_TIMEOUT_SECONDS = 0.2

# Backward-compatible exports for tests / legacy string checks.
CHUNK_PREVIEW_INDEXING = ResolvedChunkPreview.degraded(ChunkPreviewState.INDEXING).text_preview
CHUNK_PREVIEW_TIMEOUT = ResolvedChunkPreview.degraded(ChunkPreviewState.RETRIEVAL_TIMEOUT).text_preview
CHUNK_PREVIEW_HALLUCINATION = ResolvedChunkPreview.degraded(ChunkPreviewState.HALLUCINATED_ID).text_preview

CHUNK_PREVIEW_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        CHUNK_PREVIEW_INDEXING,
        CHUNK_PREVIEW_TIMEOUT,
        CHUNK_PREVIEW_HALLUCINATION,
    },
)


@runtime_checkable
class ChunkTextSource(Protocol):
    """Minimal surface for L2 chunk text lookup."""

    async def exists(self, paper_id: str) -> bool: ...

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ChunkPreviewContext:
    """Runtime hints for classifying cache misses on chunk citations."""

    paper_id: str
    vector_retrieval_timed_out: bool = False
    index_exists: bool = False
    vector_store: ChunkTextSource | None = None


def preview_from_cache(cache: dict[str, str], chunk_id: str) -> str | None:
    """Return a truncated preview when *chunk_id* is present in the L1 cache."""
    text = cache.get(chunk_id)
    if not text:
        return None
    return truncate_chunk_preview(text)


def placeholder_state_for_miss(ctx: ChunkPreviewContext | None) -> ChunkPreviewState:
    """Pick a structured preview state when preview text cannot be resolved."""
    if ctx is not None and ctx.vector_retrieval_timed_out:
        return ChunkPreviewState.RETRIEVAL_TIMEOUT
    if ctx is None or not ctx.index_exists:
        return ChunkPreviewState.INDEXING
    return ChunkPreviewState.HALLUCINATED_ID


def placeholder_for_miss(ctx: ChunkPreviewContext | None) -> str:
    """Return canonical degraded copy for a cache miss (legacy string helper)."""
    return ResolvedChunkPreview.degraded(placeholder_state_for_miss(ctx)).text_preview


def is_chunk_preview_placeholder(text: str) -> bool:
    """True when *text* is a backend-issued degradation token rather than source text."""
    return text in CHUNK_PREVIEW_PLACEHOLDERS


async def build_chunk_preview_context(
    paper_id: str,
    *,
    retrieval_warning: dict[str, str] | None = None,
    vector_store: ChunkTextSource | None = None,
) -> ChunkPreviewContext:
    """Snapshot index / timeout state once per QA stream for citation resolution."""
    timed_out = retrieval_warning is not None and retrieval_warning.get("code") == VECTOR_RETRIEVAL_TIMEOUT_CODE
    index_exists = False
    if vector_store is not None:
        try:
            index_exists = await vector_store.exists(paper_id)
        except Exception:
            logger.exception("chunk_preview index check failed paper_id=%s", paper_id)
    return ChunkPreviewContext(
        paper_id=paper_id,
        vector_retrieval_timed_out=timed_out,
        index_exists=index_exists,
        vector_store=vector_store,
    )


async def resolve_chunk_text_preview(
    chunk_id: str,
    cache: dict[str, str],
    ctx: ChunkPreviewContext | None,
) -> ResolvedChunkPreview:
    """Resolve chunk preview: L1 cache → L2 vector lookup (200 ms cap) → degraded state."""
    cached = preview_from_cache(cache, chunk_id)
    if cached:
        return ResolvedChunkPreview.ready(cached)

    if ctx is None or ctx.vector_store is None:
        return ResolvedChunkPreview.degraded(placeholder_state_for_miss(ctx))

    try:
        async with asyncio.timeout(L2_CHUNK_LOOKUP_TIMEOUT_SECONDS):
            text = await ctx.vector_store.get_chunk_text(ctx.paper_id, chunk_id)
    except TimeoutError:
        logger.debug(
            "chunk_preview L2 timeout paper_id=%s chunk_id=%s",
            ctx.paper_id,
            chunk_id,
        )
        return ResolvedChunkPreview.degraded(ChunkPreviewState.L2_TIMEOUT)
    except Exception:
        logger.exception(
            "chunk_preview L2 lookup failed paper_id=%s chunk_id=%s",
            ctx.paper_id,
            chunk_id,
        )
        return ResolvedChunkPreview.degraded(placeholder_state_for_miss(ctx))

    if text:
        cache[chunk_id] = text
        return ResolvedChunkPreview.ready(text)

    return ResolvedChunkPreview.degraded(placeholder_state_for_miss(ctx))
