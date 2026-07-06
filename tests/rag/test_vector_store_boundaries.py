"""Boundary and edge-case unit tests for VectorStore and helpers."""

from __future__ import annotations

from typing import Any

import pytest
from backend.rag.models import PaperChunk, PaperEntity, PaperRelation, VectorEvidenceType
from backend.rag.vector_store import VectorStore, clean_metadata


class FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0] for text in texts]


class FakeCollection:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.upsert_calls: int = 0
        self.query_calls: int = 0
        self.delete_calls: int = 0
        self.get_calls: int = 0

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.upsert_calls += 1
        for index, record_id in enumerate(ids):
            self.records[record_id] = {
                "document": documents[index],
                "embedding": embeddings[index],
                "metadata": metadatas[index],
            }

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.query_calls += 1
        rows = [
            (record_id, record)
            for record_id, record in self.records.items()
            if _matches_where(record["metadata"], where)
        ][:n_results]
        return {
            "ids": [[record_id for record_id, _record in rows]],
            "documents": [[record["document"] for _record_id, record in rows]],
            "metadatas": [[record["metadata"] for _record_id, record in rows]],
            "distances": [[float(index) for index, _row in enumerate(rows)]],
        }

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.get_calls += 1
        ids = [record_id for record_id, record in self.records.items() if _matches_where(record["metadata"], where)]
        return {"ids": ids[:limit]}

    def delete(self, *, where: dict[str, Any] | None = None) -> None:
        self.delete_calls += 1
        for record_id, record in list(self.records.items()):
            if _matches_where(record["metadata"], where):
                del self.records[record_id]


def _matches_where(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if where is None:
        return True
    return all(metadata.get(key) == value for key, value in where.items())


def _store() -> tuple[VectorStore, FakeCollection, FakeCollection, FakeCollection]:
    chunk_collection = FakeCollection()
    entity_collection = FakeCollection()
    relation_collection = FakeCollection()
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=chunk_collection,
        entity_collection=entity_collection,
        relation_collection=relation_collection,
    )
    return store, chunk_collection, entity_collection, relation_collection


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
async def test_index_empty_lists_does_not_call_embedding_or_upsert() -> None:
    store, chunks, entities, relations = _store()

    await store.index_chunks([])
    await store.index_entities([])
    await store.index_relations([])

    assert chunks.upsert_calls == 0
    assert entities.upsert_calls == 0
    assert relations.upsert_calls == 0


@pytest.mark.asyncio
async def test_query_with_blank_text_returns_empty() -> None:
    store, _chunks, _entities, _relations = _store()
    await store.index_chunks([_chunk("paper-1", 0, "text")])

    results = await store.query_chunks("   ", paper_id="paper-1", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_query_with_zero_top_k_returns_empty() -> None:
    store, _chunks, _entities, _relations = _store()
    await store.index_chunks([_chunk("paper-1", 0, "text")])

    results = await store.query_chunks("text", paper_id="paper-1", top_k=0)
    assert results == []


@pytest.mark.asyncio
async def test_exists_returns_false_for_unknown_paper() -> None:
    store, _chunks, _entities, _relations = _store()
    assert await store.exists("unknown-paper") is False


@pytest.mark.asyncio
async def test_delete_by_paper_is_safe_when_no_records_exist() -> None:
    store, chunks, entities, relations = _store()

    await store.delete_by_paper("unknown-paper")

    assert chunks.delete_calls == 1
    assert entities.delete_calls == 1
    assert relations.delete_calls == 1


@pytest.mark.asyncio
async def test_query_with_invalid_paper_id_raises_value_error() -> None:
    store, _chunks, _entities, _relations = _store()
    await store.index_chunks([_chunk("paper-1", 0, "alpha")])

    invalid_values: list[Any] = [None, "", "   ", 123, []]
    for invalid_value in invalid_values:
        with pytest.raises(
            ValueError,
            match="单篇 QA 路径下严禁泄露全库检索权限",
        ):
            await store.query_chunks("alpha", paper_id=invalid_value, top_k=5)


@pytest.mark.asyncio
async def test_query_entities_and_relations_also_reject_invalid_paper_id() -> None:
    store, _chunks, _entities, _relations = _store()

    for method in (store.query_entities, store.query_relations):
        with pytest.raises(ValueError, match="单篇 QA 路径下严禁泄露全库检索权限"):
            await method("x", paper_id=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_scoped_to_single_paper_returns_only_matching_paper() -> None:
    store, _chunks, _entities, _relations = _store()
    await store.index_chunks([_chunk("paper-1", 0, "alpha"), _chunk("paper-2", 0, "beta")])

    results = await store.query_chunks("alpha", paper_id="paper-1", top_k=5)

    assert len(results) == 1
    assert results[0].paper_id == "paper-1"


@pytest.mark.asyncio
async def test_clean_metadata_handles_empty_and_nested_values() -> None:
    assert clean_metadata({}) == {}
    assert clean_metadata({"none": None, "empty": ""}) == {"empty": ""}
    assert clean_metadata({"list": [1, 2, 3]}) == {"list": "[1, 2, 3]"}


@pytest.mark.asyncio
async def test_replace_paper_index_with_empty_entities_and_relations_still_indexes_chunks() -> None:
    store, chunks, entities, relations = _store()

    await store.replace_paper_index(
        "paper-1",
        chunks=[_chunk("paper-1", 0, "chunk text")],
        entities=[],
        relations=[],
    )

    assert "paper-1:chunk:0" in chunks.records
    assert entities.upsert_calls == 0
    assert relations.upsert_calls == 0


@pytest.mark.asyncio
async def test_replace_paper_index_rejects_cross_paper_evidence() -> None:
    """Cross-paper evidence must fail fast to prevent data poisoning."""

    store, chunks, entities, relations = _store()

    with pytest.raises(ValueError, match="chunk paper_id mismatch"):
        await store.replace_paper_index(
            "paper-1",
            chunks=[_chunk("paper-2", 0, "foreign chunk")],
            entities=[],
            relations=[],
        )

    # No partial writes should happen.
    assert chunks.upsert_calls == 0
    assert entities.upsert_calls == 0
    assert relations.upsert_calls == 0

    entity = PaperEntity(
        entity_id="n_foreign",
        paper_id="paper-2",
        label="Foreign",
        node_type="Method",
        description="foreign entity",
    )
    with pytest.raises(ValueError, match="entity paper_id mismatch"):
        await store.replace_paper_index(
            "paper-1",
            chunks=[_chunk("paper-1", 0, "local chunk")],
            entities=[entity],
            relations=[],
        )

    relation = PaperRelation(
        relation_id="e_foreign",
        paper_id="paper-2",
        source_id="n1",
        target_id="n2",
        relation_type="SUPPORTS",
        description="foreign relation",
    )
    with pytest.raises(ValueError, match="relation paper_id mismatch"):
        await store.replace_paper_index(
            "paper-1",
            chunks=[_chunk("paper-1", 0, "local chunk")],
            entities=[],
            relations=[relation],
        )


@pytest.mark.asyncio
async def test_replace_paper_index_accepts_all_empty_evidence_lists() -> None:
    """Replacing with no evidence is a valid no-op for the vector store."""

    store, chunks, entities, relations = _store()

    await store.replace_paper_index("paper-1", chunks=[], entities=[], relations=[])

    assert chunks.upsert_calls == 0
    assert entities.upsert_calls == 0
    assert relations.upsert_calls == 0


@pytest.mark.asyncio
async def test_replace_paper_index_rejects_mixed_legal_and_foreign_chunks() -> None:
    """A single foreign item in an otherwise valid batch must block the whole replace."""

    store, chunks, entities, relations = _store()

    with pytest.raises(ValueError, match="chunk paper_id mismatch"):
        await store.replace_paper_index(
            "paper-1",
            chunks=[_chunk("paper-1", 0, "local"), _chunk("paper-2", 1, "foreign"), _chunk("paper-1", 2, "local")],
            entities=[],
            relations=[],
        )

    # Validate short-circuit behavior: no collection wrote anything.
    assert chunks.upsert_calls == 0
    assert entities.upsert_calls == 0
    assert relations.upsert_calls == 0


@pytest.mark.asyncio
async def test_replace_paper_index_without_paper_service_validates_paper_ids() -> None:
    """The legacy fallback path must also enforce paper_id consistency."""

    store, chunks, entities, relations = _store()

    with pytest.raises(ValueError, match="chunk paper_id mismatch"):
        await store.replace_paper_index(
            "paper-1",
            chunks=[_chunk("paper-2", 0, "foreign chunk")],
            entities=[],
            relations=[],
        )

    assert chunks.upsert_calls == 0
    assert entities.upsert_calls == 0
    assert relations.upsert_calls == 0


@pytest.mark.asyncio
async def test_embedding_count_mismatch_raises_value_error() -> None:
    class MisbehavingEmbeddingClient:
        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 2.0]]  # one vector fewer than input

    store = VectorStore(
        embedding_client=MisbehavingEmbeddingClient(),
        chunk_collection=FakeCollection(),
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )

    with pytest.raises(ValueError, match="different number of vectors"):
        await store.index_chunks([_chunk("paper-1", 0, "text"), _chunk("paper-1", 1, "more")])


@pytest.mark.asyncio
async def test_query_result_parses_missing_distance_as_none() -> None:
    class NoDistanceCollection(FakeCollection):
        def query(
            self,
            *,
            query_embeddings: list[list[float]],
            n_results: int,
            where: dict[str, Any] | None = None,
            include: list[str] | None = None,
        ) -> dict[str, Any]:
            del query_embeddings, include
            rows = [
                (record_id, record)
                for record_id, record in self.records.items()
                if _matches_where(record["metadata"], where)
            ][:n_results]
            return {
                "ids": [[record_id for record_id, _record in rows]],
                "documents": [[record["document"] for _record_id, record in rows]],
                "metadatas": [[record["metadata"] for _record_id, record in rows]],
                "distances": [None],  # malformed response
            }

    chunk_collection = NoDistanceCollection()
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=chunk_collection,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )
    await store.index_chunks([_chunk("paper-1", 0, "text")])

    results = await store.query_chunks("text", paper_id="paper-1", top_k=5)

    assert len(results) == 1
    assert results[0].distance is None
    assert results[0].evidence_type == VectorEvidenceType.CHUNK


class BatchRecordingEmbeddingClient:
    """Records each embed_texts call so batching behavior can be asserted."""

    def __init__(self, batch_size: int) -> None:
        self._batch_size = batch_size
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > self._batch_size:
            raise RuntimeError(f"batch size exceeded: {len(texts)} > {self._batch_size}")
        self.calls.append(texts)
        return [[float(len(text)), 0.0] for text in texts]


@pytest.mark.asyncio
async def test_upsert_batches_embedding_calls_by_configured_batch_size() -> None:
    """Long document lists are split into embedding batches to respect API limits."""

    batch_size = 3
    embedding_client = BatchRecordingEmbeddingClient(batch_size=batch_size)
    chunk_collection = FakeCollection()
    store = VectorStore(
        embedding_client=embedding_client,
        chunk_collection=chunk_collection,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
        settings=_settings_with_embedding_batch_size(batch_size),
    )

    documents = [f"doc-{index}" for index in range(7)]
    chunks = [_chunk("paper-1", index, text) for index, text in enumerate(documents)]
    await store.index_chunks(chunks)

    assert len(embedding_client.calls) == 3  # 3 + 3 + 1
    assert [len(call) for call in embedding_client.calls] == [3, 3, 1]
    assert sum(len(call) for call in embedding_client.calls) == 7
    assert chunk_collection.upsert_calls == 1
    assert len(chunk_collection.records) == 7


@pytest.mark.asyncio
async def test_upsert_single_batch_when_documents_fit() -> None:
    """No unnecessary batching when the document count is below the batch size."""

    batch_size = 10
    embedding_client = BatchRecordingEmbeddingClient(batch_size=batch_size)
    chunk_collection = FakeCollection()
    store = VectorStore(
        embedding_client=embedding_client,
        chunk_collection=chunk_collection,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
        settings=_settings_with_embedding_batch_size(batch_size),
    )

    await store.index_chunks([_chunk("paper-1", 0, "short")])

    assert len(embedding_client.calls) == 1
    assert chunk_collection.upsert_calls == 1


@pytest.mark.asyncio
async def test_validate_evidence_paper_ids_boundary_cases() -> None:
    """Direct unit tests for the paper_id consistency helper."""

    from backend.rag.vector_store import _validate_evidence_paper_ids

    local_chunk = _chunk("paper-1", 0, "local")
    local_entity = PaperEntity(
        entity_id="n1",
        paper_id="paper-1",
        label="X",
        node_type="Method",
        description="x",
    )
    local_relation = PaperRelation(
        relation_id="e1",
        paper_id="paper-1",
        source_id="n1",
        target_id="n2",
        relation_type="SUPPORTS",
        description="x",
    )

    # Empty evidence lists are trivially consistent.
    _validate_evidence_paper_ids("paper-1", [], [], [])

    # All matching items pass.
    _validate_evidence_paper_ids(
        "paper-1",
        [local_chunk],
        [local_entity],
        [local_relation],
    )

    # Foreign chunk is caught immediately.
    with pytest.raises(ValueError, match="chunk paper_id mismatch"):
        _validate_evidence_paper_ids(
            "paper-1",
            [_chunk("paper-2", 0, "foreign"), local_chunk],
            [],
            [],
        )

    # Foreign entity is caught even when chunks are fine.
    with pytest.raises(ValueError, match="entity paper_id mismatch"):
        _validate_evidence_paper_ids(
            "paper-1",
            [local_chunk],
            [
                PaperEntity(
                    entity_id="n_bad",
                    paper_id="paper-2",
                    label="Bad",
                    node_type="Method",
                    description="bad",
                )
            ],
            [],
        )

    # Foreign relation is caught even when chunks and entities are fine.
    with pytest.raises(ValueError, match="relation paper_id mismatch"):
        _validate_evidence_paper_ids(
            "paper-1",
            [local_chunk],
            [local_entity],
            [
                PaperRelation(
                    relation_id="e_bad",
                    paper_id="paper-2",
                    source_id="n1",
                    target_id="n2",
                    relation_type="SUPPORTS",
                    description="bad",
                )
            ],
        )


def _settings_with_embedding_batch_size(batch_size: int):
    """Build a Settings instance with a custom embedding batch size for tests."""

    from backend.config import Settings

    return Settings.model_validate(
        {
            "embedding_provider": "openai",
            "embedding_batch_size": batch_size,
        }
    )
