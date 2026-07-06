"""Unit tests for the V2 RAG VectorStore wrapper."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.config import Settings
from backend.rag.models import PaperChunk, PaperEntity, PaperRelation, VectorEvidenceType
from backend.rag.vector_store import ChromaMetadata, ChromaWhere, VectorStore, clean_metadata


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text)), float(sum(ord(char) for char in text) % 97)] for text in texts]


class FakeCollection:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.last_query_n_results: int | None = None

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[ChromaMetadata],
    ) -> None:
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
        where: ChromaWhere | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.last_query_n_results = n_results
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
            "distances": [[float(index) for index, _row in enumerate(rows)]],
        }

    def get(
        self,
        *,
        where: ChromaWhere | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        del include
        ids = [record_id for record_id, record in self.records.items() if _matches_where(record["metadata"], where)]
        return {"ids": ids[:limit]}

    def delete(self, *, where: ChromaWhere | None = None) -> None:
        for record_id, record in list(self.records.items()):
            if _matches_where(record["metadata"], where):
                del self.records[record_id]


def _matches_where(metadata: ChromaMetadata, where: ChromaWhere | None) -> bool:
    if where is None:
        return True
    return all(metadata.get(key) == value for key, value in where.items())


def _store() -> tuple[VectorStore, FakeCollection, FakeCollection, FakeCollection, FakeEmbeddingClient]:
    return _store_with_settings(None)


def _store_with_settings(
    settings: Any,
) -> tuple[VectorStore, FakeCollection, FakeCollection, FakeCollection, FakeEmbeddingClient]:
    chunk_collection = FakeCollection()
    entity_collection = FakeCollection()
    relation_collection = FakeCollection()
    embedding_client = FakeEmbeddingClient()
    kwargs: dict[str, Any] = {
        "embedding_client": embedding_client,
        "chunk_collection": chunk_collection,
        "entity_collection": entity_collection,
        "relation_collection": relation_collection,
    }
    if settings is not None:
        kwargs["settings"] = settings
    store = VectorStore(**kwargs)
    return store, chunk_collection, entity_collection, relation_collection, embedding_client


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
async def test_replace_paper_index_uses_namespaced_ids_and_exists_any_evidence() -> None:
    store, chunks, entities, relations, embedding_client = _store()

    await store.replace_paper_index(
        "paper-1",
        chunks=[_chunk("paper-1", 0, "chunk text")],
        entities=[
            PaperEntity(
                paper_id="paper-1",
                entity_id="n_method",
                label="Method",
                node_type="Method",
                description="method entity",
            )
        ],
        relations=[
            PaperRelation(
                paper_id="paper-1",
                relation_id="e_supports",
                source_id="n_evidence",
                target_id="n_claim",
                relation_type="SUPPORTS",
                description="relation evidence",
            )
        ],
    )

    assert "paper-1:chunk:0" in chunks.records
    assert "paper-1:entity:n_method" in entities.records
    assert "paper-1:relation:e_supports" in relations.records
    assert await store.exists("paper-1") is True
    assert embedding_client.calls


@pytest.mark.asyncio
async def test_query_chunks_hard_filters_by_paper_id() -> None:
    store, _chunks, _entities, _relations, _embedding_client = _store()
    await store.index_chunks(
        [
            _chunk("paper-1", 0, "paper one evidence"),
            _chunk("paper-2", 0, "paper two evidence"),
        ]
    )

    results = await store.query_chunks("evidence", paper_id="paper-1", top_k=5)

    assert [result.paper_id for result in results] == ["paper-1"]
    assert results[0].evidence_type == VectorEvidenceType.CHUNK
    assert results[0].chunk_id == "paper-1:chunk:0"


@pytest.mark.asyncio
async def test_query_entities_hard_filters_by_paper_id() -> None:
    store, _chunks, entities, _relations, _embedding_client = _store()
    await store.index_entities(
        [
            PaperEntity(
                paper_id="paper-1",
                entity_id="n1",
                label="Method",
                node_type="Method",
                description="method entity",
            ),
            PaperEntity(
                paper_id="paper-2",
                entity_id="n2",
                label="Claim",
                node_type="Claim",
                description="claim entity",
            ),
        ]
    )

    results = await store.query_entities("entity", paper_id="paper-1", top_k=5)

    assert [result.paper_id for result in results] == ["paper-1"]
    assert results[0].evidence_type == VectorEvidenceType.ENTITY
    assert results[0].entity_id == "n1"


@pytest.mark.asyncio
async def test_query_relations_hard_filters_by_paper_id() -> None:
    store, _chunks, _entities, relations, _embedding_client = _store()
    await store.index_relations(
        [
            PaperRelation(
                paper_id="paper-1",
                relation_id="e1",
                source_id="n1",
                target_id="n2",
                relation_type="SUPPORTS",
                description="paper one relation",
            ),
            PaperRelation(
                paper_id="paper-2",
                relation_id="e2",
                source_id="n3",
                target_id="n4",
                relation_type="REF",
                description="paper two relation",
            ),
        ]
    )

    results = await store.query_relations("relation", paper_id="paper-1", top_k=5)

    assert [result.paper_id for result in results] == ["paper-1"]
    assert results[0].evidence_type == VectorEvidenceType.RELATION
    assert results[0].relation_id == "e1"


@pytest.mark.asyncio
async def test_query_uses_configured_default_top_k() -> None:
    """When top_k is omitted, query_* uses the configured default per collection."""

    from backend.config import Settings

    store, chunks, _entities, _relations, _embedding_client = _store_with_settings(
        Settings.model_validate(
            {
                "embedding_provider": "openai",
                "rag_top_k_chunks": 2,
                "rag_top_k_entities": 3,
                "rag_top_k_relations": 4,
            }
        )
    )
    for index in range(10):
        await store.index_chunks([_chunk("paper-1", index, f"chunk {index}")])

    await store.query_chunks("chunk", paper_id="paper-1")
    assert chunks.last_query_n_results == 2


@pytest.mark.asyncio
async def test_query_explicit_top_k_overrides_default() -> None:
    from backend.config import Settings

    store, chunks, _entities, _relations, _embedding_client = _store_with_settings(
        Settings.model_validate({"embedding_provider": "openai", "rag_top_k_chunks": 2})
    )
    await store.index_chunks([_chunk("paper-1", 0, "chunk 0"), _chunk("paper-1", 1, "chunk 1")])

    await store.query_chunks("chunk", paper_id="paper-1", top_k=1)
    assert chunks.last_query_n_results == 1


@pytest.mark.asyncio
async def test_vector_store_query_with_none_paper_id_should_raise_value_error() -> None:
    """Panic test: upstream code must never ask VectorStore to scan the whole collection."""

    store, _chunks, _entities, _relations, _embedding_client = _store()

    with pytest.raises(ValueError, match="单篇 QA 路径下严禁泄露全库检索权限") as exc_info:
        await store.query_chunks("什么是特征选择？", paper_id=None)  # type: ignore[arg-type]

    assert "paper_id 必须是非空字符串" in str(exc_info.value)

    with pytest.raises(ValueError, match="单篇 QA 路径下严禁泄露全库检索权限"):
        await store.query_chunks("什么是特征选择？", paper_id="")

    with pytest.raises(ValueError, match="单篇 QA 路径下严禁泄露全库检索权限"):
        await store.query_entities("什么是特征选择？", paper_id=None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="单篇 QA 路径下严禁泄露全库检索权限"):
        await store.query_relations("什么是特征选择？", paper_id=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_delete_by_paper_removes_all_evidence_for_one_paper() -> None:
    store, _chunks, _entities, _relations, _embedding_client = _store()
    await store.replace_paper_index(
        "paper-1",
        chunks=[_chunk("paper-1", 0, "old")],
        entities=[],
        relations=[],
    )
    await store.replace_paper_index(
        "paper-2",
        chunks=[_chunk("paper-2", 0, "other")],
        entities=[],
        relations=[],
    )

    await store.delete_by_paper("paper-1")

    assert await store.exists("paper-1") is False
    assert await store.exists("paper-2") is True


@pytest.mark.asyncio
async def test_replace_paper_index_deletes_old_records_before_upsert() -> None:
    store, chunks, _entities, _relations, _embedding_client = _store()
    await store.replace_paper_index(
        "paper-1",
        chunks=[_chunk("paper-1", 0, "old evidence"), _chunk("paper-1", 1, "stale evidence")],
        entities=[],
        relations=[],
    )

    await store.replace_paper_index(
        "paper-1",
        chunks=[_chunk("paper-1", 0, "new evidence")],
        entities=[],
        relations=[],
    )

    assert set(chunks.records) == {"paper-1:chunk:0"}
    assert chunks.records["paper-1:chunk:0"]["document"] == "new evidence"


def test_clean_metadata_removes_none_and_serializes_nested_values() -> None:
    metadata = clean_metadata(
        {
            "paper_id": "paper-1",
            "optional": None,
            "nested": {"node": "n1"},
            "count": 3,
        }
    )

    assert metadata == {
        "paper_id": "paper-1",
        "nested": '{"node": "n1"}',
        "count": 3,
    }


# ---------------------------------------------------------------------------
# Async thread-pool behavior tests
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
import time  # noqa: E402


class SlowFakeCollection(FakeCollection):
    """Fake collection that blocks the calling thread for a fixed delay."""

    def __init__(self, delay_seconds: float = 0.05) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds
        self.delete_calls = 0
        self.get_calls = 0
        self.upsert_calls = 0
        self.query_calls = 0

    def delete(self, *, where: ChromaWhere | None = None) -> None:
        self.delete_calls += 1
        time.sleep(self.delay_seconds)
        super().delete(where=where)

    def get(
        self,
        *,
        where: ChromaWhere | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.get_calls += 1
        time.sleep(self.delay_seconds)
        return super().get(where=where, limit=limit, include=include)

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[ChromaMetadata],
    ) -> None:
        self.upsert_calls += 1
        time.sleep(self.delay_seconds)
        super().upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: ChromaWhere | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.query_calls += 1
        time.sleep(self.delay_seconds)
        return super().query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
            include=include,
        )


def _slow_store(
    delay_seconds: float = 0.05,
) -> tuple[VectorStore, SlowFakeCollection, SlowFakeCollection, SlowFakeCollection, FakeEmbeddingClient]:
    chunk_collection = SlowFakeCollection(delay_seconds=delay_seconds)
    entity_collection = SlowFakeCollection(delay_seconds=delay_seconds)
    relation_collection = SlowFakeCollection(delay_seconds=delay_seconds)
    embedding_client = FakeEmbeddingClient()
    store = VectorStore(
        embedding_client=embedding_client,
        chunk_collection=chunk_collection,
        entity_collection=entity_collection,
        relation_collection=relation_collection,
    )
    return store, chunk_collection, entity_collection, relation_collection, embedding_client


@pytest.mark.asyncio
async def test_delete_by_paper_does_not_block_event_loop() -> None:
    """If delete_by_paper ran synchronously, the background coroutine could not finish first."""

    store, chunks, entities, relations, _embedding_client = _slow_store(delay_seconds=0.05)
    await store.index_chunks([_chunk("paper-1", 0, "text")])

    marker: list[str] = []

    async def background_task() -> None:
        marker.append("started")
        await asyncio.sleep(0.005)
        marker.append("done")

    task = asyncio.create_task(background_task())
    await store.delete_by_paper("paper-1")
    await task

    assert "done" in marker
    assert chunks.records == {}
    # entities/relations have no records but were still queried for deletion.
    assert entities.delete_calls >= 1
    assert relations.delete_calls >= 1


@pytest.mark.asyncio
async def test_delete_by_paper_runs_collection_deletes_concurrently() -> None:
    """Three slow deletes should complete in roughly one delay, not three."""

    store, chunks, entities, relations, _embedding_client = _slow_store(delay_seconds=0.05)
    await store.index_chunks([_chunk("paper-1", 0, "text")])

    start = time.perf_counter()
    await store.delete_by_paper("paper-1")
    elapsed = time.perf_counter() - start

    # Concurrent: should be < 0.12s even with scheduling overhead; sequential would be ~0.15s.
    assert elapsed < 0.12
    assert chunks.delete_calls >= 1
    assert entities.delete_calls >= 1
    assert relations.delete_calls >= 1


@pytest.mark.asyncio
async def test_exists_does_not_block_event_loop() -> None:
    store, chunks, entities, relations, _embedding_client = _slow_store(delay_seconds=0.05)
    await store.replace_paper_index("paper-1", chunks=[_chunk("paper-1", 0, "text")], entities=[], relations=[])

    marker: list[str] = []

    async def background_task() -> None:
        marker.append("started")
        await asyncio.sleep(0.005)
        marker.append("done")

    task = asyncio.create_task(background_task())
    result = await store.exists("paper-1")
    await task

    assert result is True
    assert "done" in marker
    assert chunks.get_calls == 1
    assert entities.get_calls == 1
    assert relations.get_calls == 1


@pytest.mark.asyncio
async def test_exists_runs_collection_gets_concurrently() -> None:
    store, chunks, _entities, _relations, _embedding_client = _slow_store(delay_seconds=0.05)
    await store.replace_paper_index("paper-1", chunks=[_chunk("paper-1", 0, "text")], entities=[], relations=[])

    start = time.perf_counter()
    await store.exists("paper-1")
    elapsed = time.perf_counter() - start

    assert elapsed < 0.12
    assert chunks.get_calls == 1


@pytest.mark.asyncio
async def test_query_runs_in_thread_and_does_not_block_event_loop() -> None:
    store, _chunks, _entities, _relations, _embedding_client = _slow_store(delay_seconds=0.05)
    await store.index_chunks([_chunk("paper-1", 0, "queryable text")])

    marker: list[str] = []

    async def background_task() -> None:
        marker.append("started")
        await asyncio.sleep(0.005)
        marker.append("done")

    task = asyncio.create_task(background_task())
    results = await store.query_chunks("query", paper_id="paper-1", top_k=5)
    await task

    assert len(results) == 1
    assert "done" in marker


@pytest.mark.asyncio
async def test_upsert_runs_in_thread_and_does_not_block_event_loop() -> None:
    store, chunks, _entities, _relations, _embedding_client = _slow_store(delay_seconds=0.05)

    marker: list[str] = []

    async def background_task() -> None:
        marker.append("started")
        await asyncio.sleep(0.005)
        marker.append("done")

    task = asyncio.create_task(background_task())
    await store.index_chunks([_chunk("paper-1", 0, "text")])
    await task

    assert "paper-1:chunk:0" in chunks.records
    assert chunks.upsert_calls == 1
    assert "done" in marker


@pytest.mark.asyncio
async def test_large_text_indexing_splits_into_correct_embedding_batches() -> None:
    """A 70-document list with batch size 32 must produce exactly 3 embed calls (32+32+6)."""

    large_documents = [f"This is chunk snippet {index}" for index in range(70)]
    mock_client = AsyncMock()
    mock_client.embed_texts.side_effect = lambda batch: [[0.1] * 1536 for _ in batch]

    settings = Settings.model_validate(
        {
            "embedding_provider": "openai",
            "embedding_batch_size": 32,
        }
    )
    store = VectorStore(
        settings=settings,
        embedding_client=mock_client,
        chunk_collection=FakeCollection(),
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )

    embeddings = await store._embed_in_batches(large_documents)

    assert len(embeddings) == 70
    assert mock_client.embed_texts.call_count == 3


# ---------------------------------------------------------------------------
# Run-id snapshot cleanup tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_replace_cleans_up_partial_orphan_run() -> None:
    """If a replace fails before activation, the partially-written run must be deleted."""

    store, chunks, entities, relations, _embedding_client = _store()

    paper_service = MagicMock()
    paper_service.get_active_run_id.return_value = "old-run"
    store._paper_service = paper_service

    cleanup_calls: list[tuple[str, str]] = []

    async def mock_cleanup_run(paper_id: str, run_id: str) -> None:
        cleanup_calls.append((paper_id, run_id))

    store._cleanup_run = mock_cleanup_run  # type: ignore[method-assign]

    def failing_upsert(**_kwargs: Any) -> None:
        raise RuntimeError("relation upsert failed")

    relations.upsert = failing_upsert  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="relation upsert failed"):
        await store.replace_paper_index(
            "paper-1",
            chunks=[_chunk("paper-1", 0, "chunk text")],
            entities=[
                PaperEntity(
                    paper_id="paper-1",
                    entity_id="n_method",
                    label="Method",
                    node_type="Method",
                    description="method entity",
                )
            ],
            relations=[
                PaperRelation(
                    paper_id="paper-1",
                    relation_id="e_supports",
                    source_id="n_evidence",
                    target_id="n_claim",
                    relation_type="SUPPORTS",
                    description="relation evidence",
                )
            ],
        )

    assert len(cleanup_calls) == 1
    cleaned_paper_id, cleaned_run_id = cleanup_calls[0]
    assert cleaned_paper_id == "paper-1"
    assert cleaned_run_id != "old-run"
    assert chunks.records
    assert entities.records
    # Relations failed before writing, so the orphan cleanup only removed
    # the successfully-written chunk/entity records for the new run.
    assert not relations.records
