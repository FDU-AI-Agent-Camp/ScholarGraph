"""C4 — query_embedding dimension and finiteness validation with embed fallback."""

from __future__ import annotations

import math
from typing import Any

import pytest
from backend.config import Settings
from backend.rag.models import VectorEvidenceType
from backend.rag.vector_store import VectorStore
from backend.rag.vector_store_utils import (
    DEFAULT_EMBEDDING_DIMENSION,
    _query_embedding_validation_issue,
    query_evidence_collection,
    resolve_query_embeddings,
)


class TrackingEmbeddingClient:
    def __init__(self, *, dimension: int = 2) -> None:
        self.dimension = dimension
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text)), 0.0] for text in texts]


class FakeCollection:
    def __init__(self) -> None:
        self.last_query_embeddings: list[list[float]] | None = None
        self.query_calls = 0

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = (n_results, where, include)
        self.query_calls += 1
        self.last_query_embeddings = query_embeddings
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.mark.parametrize(
    ("embedding", "expected_issue"),
    [
        ([], "empty"),
        ([1.0], "dimension_mismatch:1!=2"),
        ([1.0, float("nan")], "non_finite"),
        ([1.0, float("inf")], "non_finite"),
        ([1.0, 2.0], None),
    ],
)
def test_query_embedding_validation_issue_matrix(embedding: list[float], expected_issue: str | None) -> None:
    assert _query_embedding_validation_issue(embedding, expected_dimension=2) == expected_issue


@pytest.mark.asyncio
async def test_resolve_query_embeddings_uses_valid_precomputed_vector() -> None:
    client = TrackingEmbeddingClient(dimension=3)
    valid = [0.1, 0.2, 0.3]
    result = await resolve_query_embeddings("accuracy", valid, client, expected_dimension=3)
    assert result == [valid]
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_embedding",
    [
        [],
        [0.1],
        [0.1, float("nan")],
    ],
)
async def test_resolve_query_embeddings_falls_back_on_invalid_vector(
    invalid_embedding: list[float],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = TrackingEmbeddingClient()
    caplog.set_level("WARNING")
    result = await resolve_query_embeddings(
        "ImageNet top-1",
        invalid_embedding,
        client,
        expected_dimension=2,
    )
    assert result == [[14.0, 0.0]]
    assert client.calls == [["ImageNet top-1"]]
    assert "query_embedding_invalid_fallback_to_embed_text" in caplog.text


@pytest.mark.asyncio
async def test_query_evidence_collection_passes_valid_hyde_vector_to_chroma() -> None:
    client = TrackingEmbeddingClient(dimension=DEFAULT_EMBEDDING_DIMENSION)
    collection = FakeCollection()
    hyde_vector = [0.01] * DEFAULT_EMBEDDING_DIMENSION

    await query_evidence_collection(
        collection,
        client,
        "ResNet accuracy",
        evidence_type=VectorEvidenceType.CHUNK,
        paper_id="stem-001",
        top_k=2,
        query_embedding=hyde_vector,
        where={"paper_id": "stem-001"},
        expected_embedding_dimension=DEFAULT_EMBEDDING_DIMENSION,
    )

    assert collection.query_calls == 1
    assert collection.last_query_embeddings == [hyde_vector]
    assert client.calls == []


@pytest.mark.asyncio
async def test_vector_store_query_falls_back_when_hyde_dimension_mismatches(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        chromadb_path=":memory:",
        embedding_dimension=4,
    )
    client = TrackingEmbeddingClient(dimension=4)
    chunk_collection = FakeCollection()
    entity_collection = FakeCollection()
    relation_collection = FakeCollection()
    store = VectorStore(
        settings=settings,
        embedding_client=client,
        chunk_collection=chunk_collection,
        entity_collection=entity_collection,
        relation_collection=relation_collection,
    )
    caplog.set_level("WARNING")

    await store.query_chunks(
        "accuracy",
        paper_id="stem-001",
        top_k=1,
        query_embedding=[0.1, 0.2, 0.3],
    )

    assert chunk_collection.query_calls == 1
    assert chunk_collection.last_query_embeddings == [[8.0, 0.0]]
    assert client.calls == [["accuracy"]]
    assert "query_embedding_invalid_fallback_to_embed_text" in caplog.text


@pytest.mark.asyncio
async def test_vector_store_query_rejects_non_finite_without_chroma_crash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(chromadb_path=":memory:", embedding_dimension=2)
    client = TrackingEmbeddingClient(dimension=2)
    chunk_collection = FakeCollection()
    store = VectorStore(
        settings=settings,
        embedding_client=client,
        chunk_collection=chunk_collection,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )
    caplog.set_level("WARNING")

    await store.query_chunks(
        "metrics",
        paper_id="stem-001",
        query_embedding=[math.nan, 0.2],
    )

    assert chunk_collection.last_query_embeddings == [[7.0, 0.0]]
    assert client.calls == [["metrics"]]
    assert "query_embedding_invalid_fallback_to_embed_text" in caplog.text
