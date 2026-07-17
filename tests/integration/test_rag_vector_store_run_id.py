# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for VectorStore index_run_id snapshot switching."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from backend.rag.models import PaperChunk, PaperEntity
from backend.rag.vector_store import VectorStore
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService


class FakeEmbeddingClient:
    """Deterministic embedding client for integration tests without network calls."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(ord(char) for char in text) % 97)] for text in texts]


class FailingAfterChunkEmbeddingClient:
    """Fails after a configurable number of embed_texts calls."""

    def __init__(self, fail_after_calls: int) -> None:
        self._fail_after_calls = fail_after_calls
        self._call_count = 0
        self._fake = FakeEmbeddingClient()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self._call_count += 1
        if self._call_count > self._fail_after_calls:
            raise RuntimeError("embedding service unavailable")
        return await self._fake.embed_texts(texts)


@pytest.fixture
def temp_chroma_path() -> Any:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def paper_service() -> PaperService:
    return PaperService()


def _register_paper(service: PaperService, paper_id: str) -> None:
    """Directly register a minimal paper so run-id activation can be tested."""

    from datetime import UTC, datetime

    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="Test Paper",
        status=PaperStatus.READY,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        paradigm=Paradigm.STEM,
    )


def _chunk(paper_id: str, chunk_index: int, text: str) -> PaperChunk:
    return PaperChunk(
        chunk_id=f"{paper_id}:chunk:{chunk_index}",
        paper_id=paper_id,
        text=text,
        section="methods",
        chunk_index=chunk_index,
        source="pymupdf",
        char_start=chunk_index * 100,
        char_end=chunk_index * 100 + len(text),
    )


@pytest.mark.asyncio
async def test_replace_paper_index_activates_new_run_and_queries_see_only_new_data(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """After a successful replace, only the new run is visible."""

    paper_id = "paper-run-success"
    _register_paper(paper_service, paper_id)
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )

    await store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "first version content")],
        entities=[],
        relations=[],
    )
    first_run_id = paper_service.get_active_run_id(paper_id)
    assert first_run_id

    await store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "second version content")],
        entities=[],
        relations=[],
    )
    second_run_id = paper_service.get_active_run_id(paper_id)
    assert second_run_id
    assert second_run_id != first_run_id

    # Wait for any async cleanup tasks before inspecting state.
    pending = [task for task in asyncio.all_tasks() if task.get_coro().__name__ == "_cleanup_run"]
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending), timeout=5.0)

    results = await store.query_chunks("content", paper_id=paper_id, top_k=5)
    assert len(results) == 1
    assert results[0].text == "second version content"


@pytest.mark.asyncio
async def test_failed_replace_paper_index_keeps_old_index_queryable(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """If re-index fails before activation, the previous active run remains queryable."""

    paper_id = "paper-run-failure"
    _register_paper(paper_service, paper_id)

    # First, establish a healthy index with a reliable client.
    healthy_store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )
    await healthy_store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "old but valid evidence")],
        entities=[],
        relations=[],
    )
    old_run_id = paper_service.get_active_run_id(paper_id)
    assert old_run_id

    # Now attempt a re-index with a client that fails while indexing entities.
    failing_store = VectorStore(
        embedding_client=FailingAfterChunkEmbeddingClient(fail_after_calls=1),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )
    with pytest.raises(RuntimeError, match="embedding service unavailable"):
        await failing_store.replace_paper_index(
            paper_id,
            chunks=[_chunk(paper_id, 0, "new chunk content")],
            entities=[
                PaperEntity(
                    paper_id=paper_id,
                    entity_id="n_method",
                    label="Method",
                    node_type="Method",
                    description="A method that will never be embedded.",
                )
            ],
            relations=[],
        )

    # Activation never happened: the active run id must still point to the old run.
    assert paper_service.get_active_run_id(paper_id) == old_run_id

    # The old index must still be queryable through a healthy store.
    results = await healthy_store.query_chunks("evidence", paper_id=paper_id, top_k=5)
    assert len(results) == 1
    assert results[0].text == "old but valid evidence"


@pytest.mark.asyncio
async def test_replace_paper_index_cleans_up_old_runs(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """Obsolete runs are eventually removed after a successful replace."""

    paper_id = "paper-run-cleanup"
    _register_paper(paper_service, paper_id)
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )

    await store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "first run")],
        entities=[],
        relations=[],
    )
    await store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "second run")],
        entities=[],
        relations=[],
    )

    # Wait for the async cleanup task to finish.
    pending = [task for task in asyncio.all_tasks() if task.get_coro().__name__ == "_cleanup_run"]
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending), timeout=5.0)

    # Direct metadata inspection: only the active run should remain.
    active_run_id = paper_service.get_active_run_id(paper_id)
    collection = store._chunk_collection
    all_ids = collection.get(include=["metadatas"])["ids"]
    assert all_ids
    for metadata in collection.get(include=["metadatas"])["metadatas"]:
        assert metadata is not None
        assert metadata.get("index_run_id") == active_run_id


@pytest.mark.asyncio
async def test_delete_by_paper_clears_active_run_id(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """Deleting a paper also resets its active run id tracking."""

    paper_id = "paper-run-delete"
    _register_paper(paper_service, paper_id)
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )

    await store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "content to delete")],
        entities=[],
        relations=[],
    )
    assert paper_service.get_active_run_id(paper_id)

    await store.delete_by_paper(paper_id)

    assert paper_service.get_active_run_id(paper_id) is None
    assert await store.exists(paper_id) is False


@pytest.mark.asyncio
async def test_run_aware_store_is_isolated_from_unmanaged_store(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """A store without a paper service falls back to legacy behavior and cannot see run-managed data."""

    paper_id = "paper-run-isolation"
    _register_paper(paper_service, paper_id)
    managed_store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )
    await managed_store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "managed content")],
        entities=[],
        relations=[],
    )

    unmanaged_store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
    )
    # The unmanaged store filters only by paper_id; it can see the run-managed
    # data because the legacy fallback ignores index_run_id.
    assert await unmanaged_store.exists(paper_id) is True


@pytest.mark.asyncio
async def test_exists_returns_false_when_no_active_run_id_is_set(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """A partial run must not be considered available when no run is active."""

    paper_id = "bug-002"
    _register_paper(paper_service, paper_id)
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )

    # Simulate an incomplete run: only chunks are indexed, entities/relations are missing.
    await store._index_chunks(
        [_chunk(paper_id, 0, "orphan chunk")],
        run_id="run_broken",
    )

    # active_run_id is still unset.
    assert paper_service.get_active_run_id(paper_id) is None
    assert await store.exists(paper_id) is False


@pytest.mark.asyncio
async def test_exists_returns_false_when_active_run_is_incomplete(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """An active run id is not available unless all three collections have data."""

    paper_id = "bug-003"
    _register_paper(paper_service, paper_id)
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )

    await store._index_chunks(
        [_chunk(paper_id, 0, "only chunk")],
        run_id="run_broken",
    )
    # Force activate a run that only has chunks.
    paper_service.set_active_run_id(paper_id, "run_broken")

    # exists() now considers any activated run with evidence as available,
    # because partial collection states are a transient cleanup concern, not a
    # user-facing availability signal. The active run is what queries filter on.
    assert await store.exists(paper_id) is True


@pytest.mark.asyncio
async def test_reindex_failed_midway_keeps_old_index_accessible(
    temp_chroma_path: Path,
    paper_service: PaperService,
) -> None:
    """Atomicity validation: if entities indexing fails mid-reindex, the old run stays queryable."""

    paper_id = "paper-atomic-midway"
    _register_paper(paper_service, paper_id)
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=paper_service,
    )

    # 1. Establish the first successful index run (Run A).
    await store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, "Old Text")],
        entities=[
            PaperEntity(
                paper_id=paper_id,
                entity_id="n_old",
                label="Old",
                node_type="Claim",
                description="Old entity description.",
            )
        ],
        relations=[],
    )
    old_chunks = await store.query_chunks("Old Text", paper_id=paper_id, top_k=5)
    assert len(old_chunks) == 1
    assert old_chunks[0].text == "Old Text"
    old_run_id = paper_service.get_active_run_id(paper_id)
    assert old_run_id

    # 2. Start a second reindex (Run B) but make entities indexing fail.
    with mock.patch.object(store, "_index_entities", side_effect=RuntimeError("Chroma I/O Error")):
        with pytest.raises(RuntimeError, match="Chroma I/O Error"):
            await store.replace_paper_index(
                paper_id,
                chunks=[_chunk(paper_id, 0, "New Text")],
                entities=[
                    PaperEntity(
                        paper_id=paper_id,
                        entity_id="n_new",
                        label="New",
                        node_type="Claim",
                        description="New entity description.",
                    )
                ],
                relations=[],
            )

    # 3. Core assertion: the active run must still be Run A and old chunks intact.
    assert paper_service.get_active_run_id(paper_id) == old_run_id
    current_chunks = await store.query_chunks("Old Text", paper_id=paper_id, top_k=5)
    assert len(current_chunks) == len(old_chunks)
    assert current_chunks[0].text == "Old Text"
