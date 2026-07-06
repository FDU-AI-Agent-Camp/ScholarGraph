"""ChromaDB-backed vector store for RAG chunks, entities, and relations."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol, cast

from backend.rag.models import (
    EmbeddingClientProtocol,
    PaperChunk,
    PaperEntity,
    PaperRelation,
    VectorEvidenceType,
    VectorSearchResult,
)

if TYPE_CHECKING:
    from chromadb.api import ClientAPI

    from backend.config import Settings

ChromaMetadataValue = str | int | float | bool
ChromaMetadata = dict[str, ChromaMetadataValue]
ChromaWhere = dict[str, ChromaMetadataValue]


class CollectionProtocol(Protocol):
    """Subset of ChromaDB collection behavior used by VectorStore."""

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[ChromaMetadata],
    ) -> object:
        """Insert or replace vector records."""
        ...

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: ChromaWhere | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Query records by explicit embedding vector."""
        ...

    def get(
        self,
        *,
        where: ChromaWhere | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch records by metadata filter."""
        ...

    def delete(self, *, where: ChromaWhere | None = None) -> object:
        """Delete records by metadata filter."""
        ...


class VectorStore:
    """Thin ChromaDB wrapper used by downstream RAG retrieval modules."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        embedding_client: EmbeddingClientProtocol | None = None,
        chroma_path: str | None = None,
        chunk_collection: CollectionProtocol | None = None,
        entity_collection: CollectionProtocol | None = None,
        relation_collection: CollectionProtocol | None = None,
    ) -> None:
        supplied_collections = (chunk_collection, entity_collection, relation_collection)
        if any(supplied_collections) and not all(supplied_collections):
            raise ValueError("chunk_collection, entity_collection, and relation_collection must be supplied together.")

        self._embedding_client = embedding_client or _default_embedding_client(settings)
        if chunk_collection is not None and entity_collection is not None and relation_collection is not None:
            self._chunk_collection = chunk_collection
            self._entity_collection = entity_collection
            self._relation_collection = relation_collection
            return

        from backend.config import get_settings

        self._settings = settings or get_settings()
        client = _persistent_chroma_client(chroma_path or self._settings.chromadb_path)
        self._chunk_collection = cast(
            CollectionProtocol,
            client.get_or_create_collection(name=self._settings.chromadb_chunk_collection, embedding_function=None),
        )
        self._entity_collection = cast(
            CollectionProtocol,
            client.get_or_create_collection(name=self._settings.chromadb_entity_collection, embedding_function=None),
        )
        self._relation_collection = cast(
            CollectionProtocol,
            client.get_or_create_collection(name=self._settings.chromadb_relation_collection, embedding_function=None),
        )

    async def replace_paper_index(
        self,
        paper_id: str,
        *,
        chunks: list[PaperChunk],
        entities: list[PaperEntity],
        relations: list[PaperRelation],
    ) -> None:
        """Replace all indexed evidence for one paper."""

        # TODO: Later replace delete-then-upsert with index_run_id swap so a
        # failed re-index does not temporarily remove an old valid index.
        await self.delete_by_paper(paper_id)
        await self.index_chunks(chunks)
        await self.index_entities(entities)
        await self.index_relations(relations)

    async def index_chunks(self, chunks: list[PaperChunk]) -> None:
        """Upsert paper text chunks into the chunk collection."""

        documents = [chunk.text for chunk in chunks]
        ids = [chunk.chunk_id for chunk in chunks]
        metadatas = [
            clean_metadata(
                {
                    "paper_id": chunk.paper_id,
                    "evidence_type": VectorEvidenceType.CHUNK.value,
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section": chunk.section,
                    "source": chunk.source,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                }
            )
            for chunk in chunks
        ]
        await self._upsert(self._chunk_collection, ids=ids, documents=documents, metadatas=metadatas)

    async def index_entities(self, entities: list[PaperEntity]) -> None:
        """Upsert graph entities into the entity collection."""

        documents = [entity.description for entity in entities]
        ids = [_entity_chroma_id(entity.paper_id, entity.entity_id) for entity in entities]
        metadatas = [
            clean_metadata(
                {
                    "paper_id": entity.paper_id,
                    "evidence_type": VectorEvidenceType.ENTITY.value,
                    "entity_id": entity.entity_id,
                    "label": entity.label,
                    "node_type": entity.node_type,
                    "source_span": entity.source_span,
                }
            )
            for entity in entities
        ]
        await self._upsert(self._entity_collection, ids=ids, documents=documents, metadatas=metadatas)

    async def index_relations(self, relations: list[PaperRelation]) -> None:
        """Upsert graph relations into the relation collection."""

        documents = [relation.description for relation in relations]
        ids = [_relation_chroma_id(relation.paper_id, relation.relation_id) for relation in relations]
        metadatas = [
            clean_metadata(
                {
                    "paper_id": relation.paper_id,
                    "evidence_type": VectorEvidenceType.RELATION.value,
                    "relation_id": relation.relation_id,
                    "source_id": relation.source_id,
                    "target_id": relation.target_id,
                    "relation_type": relation.relation_type,
                    "rationale": relation.rationale,
                    "source_span": relation.source_span,
                }
            )
            for relation in relations
        ]
        await self._upsert(self._relation_collection, ids=ids, documents=documents, metadatas=metadatas)

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str | None = None,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Search original text chunks."""

        return await self._query(
            self._chunk_collection,
            query_text,
            evidence_type=VectorEvidenceType.CHUNK,
            paper_id=paper_id,
            top_k=top_k,
        )

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str | None = None,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Search graph entities."""

        return await self._query(
            self._entity_collection,
            query_text,
            evidence_type=VectorEvidenceType.ENTITY,
            paper_id=paper_id,
            top_k=top_k,
        )

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str | None = None,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Search graph relations."""

        return await self._query(
            self._relation_collection,
            query_text,
            evidence_type=VectorEvidenceType.RELATION,
            paper_id=paper_id,
            top_k=top_k,
        )

    async def delete_by_paper(self, paper_id: str) -> None:
        """Delete all indexed evidence for one paper from all collections."""

        where: ChromaWhere = {"paper_id": paper_id}
        await asyncio.gather(
            asyncio.to_thread(partial(self._chunk_collection.delete, where=where)),
            asyncio.to_thread(partial(self._entity_collection.delete, where=where)),
            asyncio.to_thread(partial(self._relation_collection.delete, where=where)),
        )

    async def exists(self, paper_id: str) -> bool:
        """Return true when any indexed evidence exists for the paper."""

        where: ChromaWhere = {"paper_id": paper_id}
        results = await asyncio.gather(
            asyncio.to_thread(partial(self._chunk_collection.get, where=where, limit=1, include=[])),
            asyncio.to_thread(partial(self._entity_collection.get, where=where, limit=1, include=[])),
            asyncio.to_thread(partial(self._relation_collection.get, where=where, limit=1, include=[])),
        )
        return any(_result_has_ids(result) for result in results)

    async def _upsert(
        self,
        collection: CollectionProtocol,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[ChromaMetadata],
    ) -> None:
        if not ids:
            return
        embeddings = await self._embedding_client.embed_texts(documents)
        if len(embeddings) != len(documents):
            raise ValueError("Embedding client returned a different number of vectors than input documents.")
        await asyncio.to_thread(
            partial(
                collection.upsert,
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        )

    async def _query(
        self,
        collection: CollectionProtocol,
        query_text: str,
        *,
        evidence_type: VectorEvidenceType,
        paper_id: str | None,
        top_k: int,
    ) -> list[VectorSearchResult]:
        if not query_text.strip() or top_k <= 0:
            return []

        query_embeddings = await self._embedding_client.embed_texts([query_text])
        where: ChromaWhere | None = {"paper_id": paper_id} if paper_id is not None else None
        raw_result = await asyncio.to_thread(
            partial(
                collection.query,
                query_embeddings=query_embeddings,
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        )
        return _parse_query_results(raw_result, evidence_type=evidence_type)


def clean_metadata(metadata: dict[str, object]) -> ChromaMetadata:
    """Remove None values and coerce nested metadata into Chroma-safe scalars."""

    cleaned: ChromaMetadata = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, bool | int | float | str):
            cleaned[key] = value
        else:
            cleaned[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return cleaned


def _entity_chroma_id(paper_id: str, entity_id: str) -> str:
    return f"{paper_id}:entity:{entity_id}"


def _relation_chroma_id(paper_id: str, relation_id: str) -> str:
    return f"{paper_id}:relation:{relation_id}"


def _persistent_chroma_client(path: str) -> ClientAPI:
    """Create a local persistent Chroma client with a strongly typed return."""
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("chromadb is required for VectorStore; install project dependencies first.") from exc
    # PersistentClient returns a concrete ClientAPI implementation, but pyright
    # cannot infer the return type from the dynamic chromadb package.
    return chromadb.PersistentClient(path=path)  # type: ignore[return-value]


def _default_embedding_client(settings: Settings | None) -> EmbeddingClientProtocol:
    if settings is not None:
        from backend.llm.embeddings import EmbeddingClient

        return EmbeddingClient(settings)

    from backend.llm.embeddings import get_embedding_client

    return get_embedding_client()


def _parse_query_results(raw_result: dict[str, Any], *, evidence_type: VectorEvidenceType) -> list[VectorSearchResult]:
    ids = _first_query_batch(raw_result.get("ids"))
    documents = _first_query_batch(raw_result.get("documents"))
    metadatas = _first_query_batch(raw_result.get("metadatas"))
    distances = _first_query_batch(raw_result.get("distances"))

    results: list[VectorSearchResult] = []
    for index, result_id in enumerate(ids):
        metadata = clean_metadata(_item_at(metadatas, index, default={}))
        text = str(_item_at(documents, index, default=""))
        distance = _item_at(distances, index, default=None)
        results.append(
            VectorSearchResult(
                id=str(result_id),
                paper_id=str(metadata.get("paper_id", "")),
                evidence_type=evidence_type,
                text=text,
                metadata=metadata,
                distance=float(distance) if isinstance(distance, int | float) else None,
            )
        )
    return results


def _first_query_batch(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else value


def _item_at(items: list[Any], index: int, *, default: Any) -> Any:
    return items[index] if index < len(items) else default


def _result_has_ids(result: dict[str, Any]) -> bool:
    ids = result.get("ids")
    if isinstance(ids, list):
        if not ids:
            return False
        if isinstance(ids[0], list):
            return bool(ids[0])
        return True
    return False
