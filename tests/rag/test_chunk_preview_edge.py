"""B10 adversarial edge matrix — mock time/space gaps, never emit bare empty preview."""

from __future__ import annotations

import asyncio
import time

import pytest
from backend.graph.qa_v2 import build_chunk_text_cache, dispatch_citation_async
from backend.rag.chunk_preview import (
    ChunkPreviewContext,
    build_chunk_preview_context,
    resolve_chunk_text_preview,
)
from backend.rag.models import RetrievedChunk
from backend.schemas.chunk_preview import (
    CHUNK_PREVIEW_STATE_MESSAGES,
    CHUNK_TEXT_PREVIEW_MAX_CHARS,
    ChunkPreviewState,
)


class CollectionNotFoundError(Exception):
    """Stand-in for Chroma collection missing during cold-start ingest."""


def _assert_preview_never_empty(text_preview: str) -> None:
    assert text_preview != ""
    assert text_preview.strip() != ""


class _TimedChunkStore:
    """Configurable mock VectorStore surface for L2 adversarial injection."""

    def __init__(
        self,
        *,
        exists: bool = True,
        exists_raises: type[Exception] | None = None,
        texts: dict[str, str] | None = None,
        delay_seconds: float = 0.0,
        lookup_raises: type[Exception] | None = None,
    ) -> None:
        self._exists = exists
        self._exists_raises = exists_raises
        self._texts = texts or {}
        self._delay_seconds = delay_seconds
        self._lookup_raises = lookup_raises
        self.lookup_calls = 0

    async def exists(self, paper_id: str) -> bool:
        _ = paper_id
        if self._exists_raises is not None:
            raise self._exists_raises("paper_chunks collection not found")
        return self._exists

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        _ = paper_id
        self.lookup_calls += 1
        if self._lookup_raises is not None:
            raise self._lookup_raises("paper_chunks collection not found")
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        return self._texts.get(chunk_id)


def _empty_retrieval_chunk_cache() -> dict[str, str]:
    """Simulate graph-only fallback: RC.chunks was empty at retrieve time."""
    return build_chunk_text_cache([])


def _graph_only_preview_ctx(
    paper_id: str,
    store: _TimedChunkStore,
    *,
    vector_retrieval_timed_out: bool = False,
    index_exists: bool | None = None,
) -> ChunkPreviewContext:
    resolved_index = store._exists if index_exists is None else index_exists
    return ChunkPreviewContext(
        paper_id=paper_id,
        vector_retrieval_timed_out=vector_retrieval_timed_out,
        index_exists=resolved_index,
        vector_store=store,
    )


@pytest.mark.asyncio
async def test_edge_scenario_1_l2_rescue_after_empty_retrieval_context() -> None:
    """① L1 empty (RC.chunks miss) + fast L2 hit → ready preview, max 120 chars.

    Delay is zero so full-suite load cannot turn a successful rescue into L2_TIMEOUT
    (fuse is 200ms; 50ms sleep was flaky under concurrent pytest pressure).
    """
    paper_id = "stem-001"
    chunk_id = "stem-001:chunk:42"
    source_text = (
        "We evaluate ResNet-Light on the ImageNet validation set. "
        "The proposed model achieves a top-1 accuracy of 78.5%, outperforming the prior CNN baseline."
    )
    store = _TimedChunkStore(texts={chunk_id: source_text}, delay_seconds=0.0)
    cache = _empty_retrieval_chunk_cache()
    ctx = _graph_only_preview_ctx(
        paper_id,
        store,
        vector_retrieval_timed_out=True,
        index_exists=True,
    )

    resolved = await resolve_chunk_text_preview(chunk_id, cache, ctx)
    evt = await dispatch_citation_async(
        "chunk:",
        chunk_id,
        paper_id,
        {},
        {},
        cache,
        preview_ctx=ctx,
    )

    assert store.lookup_calls >= 1
    assert resolved.preview_state == ChunkPreviewState.READY
    assert resolved.text_preview == source_text[:CHUNK_TEXT_PREVIEW_MAX_CHARS]
    assert "78.5%" in resolved.text_preview
    _assert_preview_never_empty(resolved.text_preview)
    assert evt.data["text_preview"] == resolved.text_preview
    assert evt.data["preview_state"] == ChunkPreviewState.READY
    assert cache[chunk_id] == source_text


@pytest.mark.asyncio
async def test_edge_scenario_2_processing_cold_start_collection_not_found() -> None:
    """② PROCESSING / missing Chroma collection → indexing placeholder, never blank."""
    paper_id = "stem-002"
    chunk_id = "stem-002_chunk_1"
    store = _TimedChunkStore(
        exists=False,
        exists_raises=CollectionNotFoundError,
        lookup_raises=CollectionNotFoundError,
    )
    cache = _empty_retrieval_chunk_cache()
    ctx = _graph_only_preview_ctx(paper_id, store, index_exists=False)

    expected = CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.INDEXING]
    resolved = await resolve_chunk_text_preview(chunk_id, cache, ctx)
    evt = await dispatch_citation_async(
        "chunk:",
        chunk_id,
        paper_id,
        {},
        {},
        cache,
        preview_ctx=ctx,
    )

    assert resolved.preview_state == ChunkPreviewState.INDEXING
    assert resolved.text_preview == expected
    _assert_preview_never_empty(resolved.text_preview)
    assert evt.data["preview_state"] == ChunkPreviewState.INDEXING
    assert evt.data["text_preview"] == expected


@pytest.mark.asyncio
async def test_edge_scenario_2_build_context_survives_exists_collection_error() -> None:
    """② build_chunk_preview_context treats Chroma exists() failure as index missing."""
    store = _TimedChunkStore(exists_raises=CollectionNotFoundError)
    ctx = await build_chunk_preview_context("stem-002", vector_store=store)
    assert ctx.index_exists is False


@pytest.mark.asyncio
async def test_edge_scenario_3_l2_micro_timeout_fuses_before_slow_lookup_finishes() -> None:
    """③ get_chunk_text sleeps 300ms → L2 fuse ≤200ms, timeout placeholder emitted."""
    paper_id = "stem-001"
    chunk_id = "stem-001:chunk:42"
    store = _TimedChunkStore(
        texts={chunk_id: "This text must not appear after fuse."},
        delay_seconds=0.3,
        exists=True,
    )
    cache = _empty_retrieval_chunk_cache()
    ctx = _graph_only_preview_ctx(paper_id, store, index_exists=True)

    expected = CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.L2_TIMEOUT]
    started = time.perf_counter()
    resolved = await resolve_chunk_text_preview(chunk_id, cache, ctx)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.28, f"L2 fuse must not wait full 300ms sleep, took {elapsed:.3f}s"
    assert resolved.preview_state == ChunkPreviewState.L2_TIMEOUT
    assert resolved.text_preview == expected
    _assert_preview_never_empty(resolved.text_preview)
    assert chunk_id not in cache

    evt = await dispatch_citation_async(
        "chunk:",
        chunk_id,
        paper_id,
        {},
        {},
        cache,
        preview_ctx=ctx,
    )
    assert evt.data["preview_state"] in {
        ChunkPreviewState.L2_TIMEOUT,
        ChunkPreviewState.RETRIEVAL_TIMEOUT,
    }
    assert evt.data["text_preview"] == expected


@pytest.mark.asyncio
async def test_edge_scenario_4_hallucinated_chunk_id_on_indexed_paper() -> None:
    """④ Fake stem-001_chunk_99999 on indexed paper → hallucinated_id warning."""
    paper_id = "stem-001"
    chunk_id = "stem-001_chunk_99999"
    store = _TimedChunkStore(exists=True, texts={})
    cache = _empty_retrieval_chunk_cache()
    ctx = _graph_only_preview_ctx(paper_id, store, index_exists=True)

    expected = CHUNK_PREVIEW_STATE_MESSAGES[ChunkPreviewState.HALLUCINATED_ID]
    resolved = await resolve_chunk_text_preview(chunk_id, cache, ctx)
    evt = await dispatch_citation_async(
        "chunk:",
        chunk_id,
        paper_id,
        {},
        {},
        cache,
        preview_ctx=ctx,
    )

    assert store.lookup_calls >= 1
    assert resolved.preview_state == ChunkPreviewState.HALLUCINATED_ID
    assert resolved.text_preview == expected
    _assert_preview_never_empty(resolved.text_preview)
    assert evt.data["preview_state"] == ChunkPreviewState.HALLUCINATED_ID
    assert evt.data["text_preview"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunk_id", "store_factory"),
    [
        (
            "stem-001:chunk:42",
            lambda: _TimedChunkStore(
                texts={
                    "stem-001:chunk:42": "ResNet-Light top-1 accuracy 78.5% on ImageNet validation split.",
                },
                delay_seconds=0.0,
            ),
        ),
        (
            "stem-002_chunk_1",
            lambda: _TimedChunkStore(exists=False, exists_raises=CollectionNotFoundError),
        ),
        (
            "stem-001:chunk:42",
            lambda: _TimedChunkStore(
                texts={"stem-001:chunk:42": "blocked"},
                delay_seconds=0.3,
            ),
        ),
        (
            "stem-001_chunk_99999",
            lambda: _TimedChunkStore(exists=True, texts={}),
        ),
    ],
    ids=["l2-rescue", "cold-indexing", "l2-fuse", "hallucination"],
)
async def test_edge_matrix_never_emits_bare_empty_string_via_sse_dispatch(
    chunk_id: str,
    store_factory: object,
) -> None:
    """Regression: all four adversarial injections must yield non-empty text_preview on SSE path."""
    store = store_factory()  # type: ignore[operator]
    paper_id = "stem-001" if chunk_id.startswith("stem-001") else "stem-002"
    cache = _empty_retrieval_chunk_cache()
    ctx = _graph_only_preview_ctx(
        paper_id,
        store,
        vector_retrieval_timed_out=(paper_id == "stem-001" and "99999" not in chunk_id),
        index_exists=getattr(store, "_exists", True),
    )

    evt = await dispatch_citation_async(
        "chunk:",
        chunk_id,
        paper_id,
        {},
        {},
        cache,
        preview_ctx=ctx,
    )
    _assert_preview_never_empty(evt.data["text_preview"])
    assert evt.data["preview_state"] in {state.value for state in ChunkPreviewState}


def test_edge_retrieval_context_chunks_empty_does_not_seed_l1_cache() -> None:
    """Space gap: empty RC.chunks must not pre-populate L1 (forces L2 on cite)."""
    rc_chunks: list[RetrievedChunk] = []
    cache = build_chunk_text_cache(rc_chunks)
    assert cache == {}
