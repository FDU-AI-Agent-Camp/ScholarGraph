"""Robustness integration tests for VectorStore against real ChromaDB."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from backend.rag.models import PaperChunk, PaperEntity, PaperRelation
from backend.rag.vector_store import VectorStore


class FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(ord(char) for char in text) % 97)] for text in texts]


@pytest.fixture
def temp_chroma_path() -> Any:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
async def store(temp_chroma_path: Path) -> VectorStore:
    return VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
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
async def test_repeated_reindex_does_not_leave_stale_records(store: VectorStore) -> None:
    """Re-indexing the same paper many times must remain idempotent."""

    for iteration in range(5):
        await store.replace_paper_index(
            "paper-1",
            chunks=[_chunk("paper-1", 0, f"iteration {iteration}")],
            entities=[],
            relations=[],
        )

    results = await store.query_chunks("iteration", paper_id="paper-1", top_k=10)
    assert len(results) == 1
    assert results[0].text == "iteration 4"


@pytest.mark.asyncio
async def test_large_text_indexing_does_not_crash(store: VectorStore) -> None:
    large_text = "word " * 5000  # ~30k chars

    await store.replace_paper_index(
        "paper-large",
        chunks=[_chunk("paper-large", 0, large_text)],
        entities=[],
        relations=[],
    )

    assert await store.exists("paper-large") is True


@pytest.mark.asyncio
async def test_empty_chunks_entities_relations_can_be_indexed(store: VectorStore) -> None:
    await store.replace_paper_index("paper-empty", chunks=[], entities=[], relations=[])

    assert await store.exists("paper-empty") is False


@pytest.mark.asyncio
async def test_concurrent_indexing_of_same_paper_is_safe(store: VectorStore) -> None:
    async def index_batch(batch_index: int) -> None:
        await store.replace_paper_index(
            "paper-concurrent",
            chunks=[_chunk("paper-concurrent", batch_index, f"batch {batch_index}")],
            entities=[],
            relations=[],
        )

    await asyncio.gather(*(index_batch(i) for i in range(5)))

    assert await store.exists("paper-concurrent") is True


@pytest.mark.asyncio
async def test_concurrent_indexing_of_different_papers_is_isolated(store: VectorStore) -> None:
    async def index_paper(paper_id: str) -> None:
        await store.replace_paper_index(
            paper_id,
            chunks=[_chunk(paper_id, 0, f"content for {paper_id}")],
            entities=[],
            relations=[],
        )

    paper_ids = [f"paper-{i}" for i in range(10)]
    await asyncio.gather(*(index_paper(paper_id) for paper_id in paper_ids))

    for paper_id in paper_ids:
        assert await store.exists(paper_id) is True
        results = await store.query_chunks(f"content for {paper_id}", paper_id=paper_id, top_k=1)
        assert len(results) == 1
        assert results[0].paper_id == paper_id


@pytest.mark.asyncio
async def test_query_unknown_paper_returns_empty(store: VectorStore) -> None:
    await store.index_chunks([_chunk("paper-known", 0, "known content")])

    results = await store.query_chunks("known", paper_id="paper-unknown", top_k=5)

    assert results == []


@pytest.mark.asyncio
async def test_delete_by_paper_is_idempotent(store: VectorStore) -> None:
    await store.index_chunks([_chunk("paper-1", 0, "text")])

    await store.delete_by_paper("paper-1")
    await store.delete_by_paper("paper-1")
    await store.delete_by_paper("paper-1")

    assert await store.exists("paper-1") is False


@pytest.mark.asyncio
async def test_entity_and_relation_with_empty_graph_parts(store: VectorStore) -> None:
    """Entities and relations with minimal fields still round-trip through ChromaDB."""

    await store.replace_paper_index(
        "paper-minimal",
        chunks=[],
        entities=[
            PaperEntity(
                paper_id="paper-minimal",
                entity_id="n_1",
                label="X",
                node_type="Concept",
                description="Minimal entity.",
            )
        ],
        relations=[
            PaperRelation(
                paper_id="paper-minimal",
                relation_id="e_1",
                source_id="n_1",
                target_id="n_2",
                relation_type="RELATES_TO",
                description="Minimal relation.",
            )
        ],
    )

    entity_results = await store.query_entities("Minimal entity", paper_id="paper-minimal", top_k=5)
    relation_results = await store.query_relations("Minimal relation", paper_id="paper-minimal", top_k=5)

    assert len(entity_results) == 1
    assert len(relation_results) == 1
