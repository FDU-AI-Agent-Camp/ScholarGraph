# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B10 — chunk text_preview L2 lazy lookup and structured placeholders."""

from __future__ import annotations

import asyncio

import pytest
from backend.graph.qa_v2 import dispatch_citation, dispatch_citation_async
from backend.rag.chunk_preview import (
    CHUNK_PREVIEW_HALLUCINATION,
    CHUNK_PREVIEW_INDEXING,
    CHUNK_PREVIEW_TIMEOUT,
    ChunkPreviewContext,
    build_chunk_preview_context,
    placeholder_for_miss,
    resolve_chunk_text_preview,
)
from backend.rag.static_mock_vector_store import StaticMockVectorStore
from backend.schemas.chunk_preview import ChunkPreviewState
from backend.services.qa_retrieval import VECTOR_RETRIEVAL_TIMEOUT_CODE


class _StubChunkStore:
    def __init__(
        self,
        *,
        exists: bool = True,
        texts: dict[str, str] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._exists = exists
        self._texts = texts or {}
        self._delay_seconds = delay_seconds
        self.lookup_calls: list[tuple[str, str]] = []

    async def exists(self, paper_id: str) -> bool:
        _ = paper_id
        return self._exists

    async def get_chunk_text(self, paper_id: str, chunk_id: str) -> str | None:
        self.lookup_calls.append((paper_id, chunk_id))
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        return self._texts.get(chunk_id)


@pytest.mark.asyncio
async def test_resolve_chunk_preview_cache_hit_skips_l2() -> None:
    cache = {"c1": "Cached chunk body."}
    ctx = ChunkPreviewContext(paper_id="p1", index_exists=True, vector_store=_StubChunkStore())
    preview = await resolve_chunk_text_preview("c1", cache, ctx)
    assert preview.text_preview == "Cached chunk body."
    assert preview.preview_state == ChunkPreviewState.READY
    assert ctx.vector_store is not None
    assert isinstance(ctx.vector_store, _StubChunkStore)
    assert ctx.vector_store.lookup_calls == []


@pytest.mark.asyncio
async def test_resolve_chunk_preview_l2_backfills_cache() -> None:
    store = _StubChunkStore(texts={"c2": "Lazy loaded text."})
    cache: dict[str, str] = {}
    ctx = ChunkPreviewContext(paper_id="p1", index_exists=True, vector_store=store)
    preview = await resolve_chunk_text_preview("c2", cache, ctx)
    assert preview.text_preview == "Lazy loaded text."
    assert preview.preview_state == ChunkPreviewState.READY
    assert cache["c2"] == "Lazy loaded text."
    assert store.lookup_calls == [("p1", "c2")]


@pytest.mark.asyncio
async def test_resolve_chunk_preview_l2_timeout_state() -> None:
    store = _StubChunkStore(texts={"c2": "Never returned."}, delay_seconds=0.5)
    cache: dict[str, str] = {}
    ctx = ChunkPreviewContext(paper_id="p1", index_exists=True, vector_store=store)
    preview = await resolve_chunk_text_preview("c2", cache, ctx)
    assert preview.preview_state == ChunkPreviewState.L2_TIMEOUT
    assert preview.text_preview == CHUNK_PREVIEW_TIMEOUT


@pytest.mark.asyncio
async def test_resolve_chunk_preview_hallucinated_id_when_index_ready() -> None:
    store = _StubChunkStore(exists=True, texts={})
    cache: dict[str, str] = {}
    ctx = ChunkPreviewContext(paper_id="p1", index_exists=True, vector_store=store)
    preview = await resolve_chunk_text_preview("missing", cache, ctx)
    assert preview.preview_state == ChunkPreviewState.HALLUCINATED_ID
    assert preview.text_preview == CHUNK_PREVIEW_HALLUCINATION


@pytest.mark.asyncio
async def test_resolve_chunk_preview_indexing_when_index_missing() -> None:
    store = _StubChunkStore(exists=False, texts={})
    cache: dict[str, str] = {}
    ctx = ChunkPreviewContext(paper_id="p1", index_exists=False, vector_store=store)
    preview = await resolve_chunk_text_preview("c1", cache, ctx)
    assert preview.preview_state == ChunkPreviewState.INDEXING
    assert preview.text_preview == CHUNK_PREVIEW_INDEXING


@pytest.mark.asyncio
async def test_build_chunk_preview_context_marks_timeout_warning() -> None:
    store = _StubChunkStore(exists=True)
    ctx = await build_chunk_preview_context(
        "p1",
        retrieval_warning={"code": VECTOR_RETRIEVAL_TIMEOUT_CODE, "message": "timeout"},
        vector_store=store,
    )
    assert ctx.vector_retrieval_timed_out is True
    assert ctx.index_exists is True


def test_placeholder_for_miss_priority_timeout_over_indexing() -> None:
    ctx = ChunkPreviewContext(paper_id="p1", vector_retrieval_timed_out=True, index_exists=False)
    assert placeholder_for_miss(ctx) == CHUNK_PREVIEW_TIMEOUT


def test_dispatch_citation_never_emits_empty_chunk_preview() -> None:
    evt = dispatch_citation("chunk:", "missing", "p1", {}, {}, {})
    assert evt.data["text_preview"] == CHUNK_PREVIEW_HALLUCINATION
    assert evt.data["preview_state"] == ChunkPreviewState.HALLUCINATED_ID


@pytest.mark.asyncio
async def test_dispatch_citation_async_uses_l2_lookup() -> None:
    store = _StubChunkStore(texts={"c9": "From vector store."})
    ctx = ChunkPreviewContext(paper_id="p1", index_exists=True, vector_store=store)
    evt = await dispatch_citation_async("chunk:", "c9", "p1", {}, {}, {}, preview_ctx=ctx)
    assert evt.data["type"] == "chunk"
    assert evt.data["text_preview"] == "From vector store."
    assert evt.data["preview_state"] == ChunkPreviewState.READY


@pytest.mark.asyncio
async def test_dispatch_citation_async_truncates_long_preview() -> None:
    long_text = "x" * 200
    store = _StubChunkStore(texts={"c1": long_text})
    ctx = ChunkPreviewContext(paper_id="p1", index_exists=True, vector_store=store)
    evt = await dispatch_citation_async("chunk:", "c1", "p1", {}, {}, {}, preview_ctx=ctx)
    assert len(evt.data["text_preview"]) == 120
    assert evt.data["preview_state"] == ChunkPreviewState.READY


@pytest.mark.asyncio
async def test_static_mock_vector_store_lru_avoids_repeat_scan() -> None:
    from backend.rag.models import RetrievedChunk

    chunk = RetrievedChunk(
        id="mock:p1:c1",
        paper_id="p1",
        text="Fixture chunk.",
        chunk_id="c1",
        chunk_index=0,
        char_start=0,
        char_end=14,
    )
    store = StaticMockVectorStore({"p1": [chunk]})
    assert await store.get_chunk_text("p1", "c1") == "Fixture chunk."
    assert await store.get_chunk_text("p1", "c1") == "Fixture chunk."
    info = store._get_chunk_text_cached.cache_info()
    assert info.hits >= 1
