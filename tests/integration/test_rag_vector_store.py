"""Integration tests for VectorStore against a real ChromaDB instance."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from backend.rag.models import PaperChunk, PaperEntity, PaperRelation, VectorEvidenceType
from backend.rag.vector_store import VectorStore


class FakeEmbeddingClient:
    """Deterministic embedding client for integration tests without network calls."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(ord(char) for char in text) % 97)] for text in texts]


@pytest.fixture
def temp_chroma_path() -> Any:
    # ChromaDB holds file handles on Windows; ignore_cleanup_errors prevents
    # teardown failures while still deleting what can be deleted.
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
async def test_real_chroma_index_and_query_chunks(store: VectorStore) -> None:
    await store.index_chunks(
        [
            _chunk("paper-1", 0, "neural network architecture for citation graphs"),
            _chunk("paper-1", 1, "experimental results show strong retrieval improvement"),
        ]
    )

    results = await store.query_chunks("neural network", paper_id="paper-1", top_k=5)

    assert len(results) >= 1
    assert all(result.paper_id == "paper-1" for result in results)
    assert results[0].evidence_type == VectorEvidenceType.CHUNK
    assert any("neural" in result.text.lower() for result in results)


@pytest.mark.asyncio
async def test_real_chroma_paper_isolation(store: VectorStore) -> None:
    await store.index_chunks(
        [
            _chunk("paper-a", 0, "unique content alpha"),
            _chunk("paper-b", 0, "unique content beta"),
        ]
    )

    alpha_results = await store.query_chunks("alpha", paper_id="paper-a", top_k=5)
    beta_results = await store.query_chunks("beta", paper_id="paper-b", top_k=5)

    assert all(result.paper_id == "paper-a" for result in alpha_results)
    assert all(result.paper_id == "paper-b" for result in beta_results)
    assert "beta" not in {result.text.lower() for result in alpha_results}
    assert "alpha" not in {result.text.lower() for result in beta_results}


@pytest.mark.asyncio
async def test_real_chroma_delete_by_paper_isolates_other_papers(store: VectorStore) -> None:
    await store.index_chunks(
        [
            _chunk("paper-a", 0, "alpha evidence"),
            _chunk("paper-b", 0, "beta evidence"),
        ]
    )

    await store.delete_by_paper("paper-a")

    assert await store.exists("paper-a") is False
    assert await store.exists("paper-b") is True


@pytest.mark.asyncio
async def test_real_chroma_replace_paper_index_is_idempotent(store: VectorStore) -> None:
    await store.replace_paper_index(
        "paper-1",
        chunks=[_chunk("paper-1", 0, "old evidence")],
        entities=[],
        relations=[],
    )

    await store.replace_paper_index(
        "paper-1",
        chunks=[_chunk("paper-1", 0, "new evidence")],
        entities=[],
        relations=[],
    )

    results = await store.query_chunks("evidence", paper_id="paper-1", top_k=5)
    assert len(results) == 1
    assert results[0].text == "new evidence"


@pytest.mark.asyncio
async def test_real_chroma_entities_and_relations_round_trip(store: VectorStore) -> None:
    await store.replace_paper_index(
        "paper-1",
        chunks=[],
        entities=[
            PaperEntity(
                paper_id="paper-1",
                entity_id="n_method",
                label="GraphRAG",
                node_type="Method",
                description="GraphRAG retrieves evidence from a knowledge graph.",
            )
        ],
        relations=[
            PaperRelation(
                paper_id="paper-1",
                relation_id="e_supports",
                source_id="n_method",
                target_id="n_claim",
                relation_type="SUPPORTS",
                description="GraphRAG SUPPORTS improved retrieval.",
            )
        ],
    )

    entity_results = await store.query_entities("knowledge graph", paper_id="paper-1", top_k=5)
    relation_results = await store.query_relations("retrieval", paper_id="paper-1", top_k=5)

    assert any(result.metadata.get("entity_id") == "n_method" for result in entity_results)
    assert any(result.metadata.get("relation_id") == "e_supports" for result in relation_results)


@pytest.mark.asyncio
async def test_real_chroma_concurrent_operations_do_not_corrupt_state(store: VectorStore) -> None:
    await store.index_chunks([_chunk("paper-1", 0, "shared evidence")])

    async def query_repeatedly() -> None:
        for _ in range(5):
            await store.query_chunks("evidence", paper_id="paper-1", top_k=5)

    async def delete_and_reindex() -> None:
        await store.delete_by_paper("paper-1")
        await store.index_chunks([_chunk("paper-1", 0, "reindexed evidence")])

    await asyncio.gather(query_repeatedly(), delete_and_reindex())

    final_results = await store.query_chunks("evidence", paper_id="paper-1", top_k=5)
    assert len(final_results) >= 1
    assert any("reindexed" in result.text for result in final_results)


@pytest.mark.asyncio
async def test_real_chroma_query_does_not_block_event_loop(store: VectorStore) -> None:
    await store.index_chunks([_chunk("paper-1", 0, "some searchable text")])

    marker: list[str] = []

    async def background() -> None:
        marker.append("started")
        await asyncio.sleep(0.005)
        marker.append("done")

    task = asyncio.create_task(background())
    await store.query_chunks("searchable", paper_id="paper-1", top_k=5)
    await task

    assert "done" in marker


@pytest.mark.asyncio
async def test_real_chroma_query_uses_configured_default_top_k(temp_chroma_path: Path) -> None:
    """When top_k is omitted, VectorStore reads defaults from settings."""

    from backend.config import Settings

    settings = Settings.model_validate(
        {
            "embedding_provider": "openai",
            "rag_top_k_chunks": 2,
            "rag_top_k_entities": 2,
            "rag_top_k_relations": 2,
        }
    )
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        settings=settings,
    )
    await store.index_chunks([_chunk("paper-1", index, f"chunk {index}") for index in range(10)])

    results = await store.query_chunks("chunk", paper_id="paper-1")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_real_chroma_explicit_top_k_overrides_configured_default(temp_chroma_path: Path) -> None:
    from backend.config import Settings

    settings = Settings.model_validate(
        {
            "embedding_provider": "openai",
            "rag_top_k_chunks": 2,
        }
    )
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        settings=settings,
    )
    await store.index_chunks([_chunk("paper-1", index, f"chunk {index}") for index in range(10)])

    results = await store.query_chunks("chunk", paper_id="paper-1", top_k=7)
    assert len(results) == 7
