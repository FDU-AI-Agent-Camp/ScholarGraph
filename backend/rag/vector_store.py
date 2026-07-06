"""ChromaDB-backed vector store for RAG chunks, entities, and relations."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from typing import TYPE_CHECKING, cast

from backend.rag.models import (
    EmbeddingClientProtocol,
    PaperChunk,
    PaperEntity,
    PaperRelation,
    VectorEvidenceType,
)
from backend.rag.vector_store_utils import (
    ChromaMetadata,
    ChromaWhere,
    CollectionProtocol,
    RawMetadata,
    _chunk_chroma_id,
    _default_embedding_client,
    _entity_chroma_id,
    _generate_run_id,
    _parse_query_results,
    _persistent_chroma_client,
    _relation_chroma_id,
    _result_has_ids,
    clean_metadata,
)

if TYPE_CHECKING:
    from backend.config import Settings
    from backend.services.paper_service import PaperService

__all__ = [
    "ChromaMetadata",
    "ChromaWhere",
    "CollectionProtocol",
    "VectorStore",
    "clean_metadata",
]


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
        paper_service: PaperService | None = None,
    ) -> None:
        supplied_collections = (chunk_collection, entity_collection, relation_collection)
        if any(supplied_collections) and not all(supplied_collections):
            raise ValueError("chunk_collection, entity_collection, and relation_collection must be supplied together.")

        self._embedding_client = embedding_client or _default_embedding_client(settings)
        self._paper_service = paper_service
        self._pending_cleanups: dict[str, set[asyncio.Task[None]]] = {}
        if chunk_collection is not None and entity_collection is not None and relation_collection is not None:
            self._chunk_collection = chunk_collection
            self._entity_collection = entity_collection
            self._relation_collection = relation_collection
            return

        from backend.config import get_settings

        self._settings = settings or get_settings()
        resolved_chroma_path = chroma_path or self._settings.chromadb_path
        if chroma_path is None and "pytest" in sys.modules:
            raise RuntimeError(
                "CRITICAL: VectorStore must be initialized with an explicit isolated "
                "chroma_path in tests. Passing the default persistence directory would "
                "pollute the development environment."
            )
        client = _persistent_chroma_client(resolved_chroma_path)
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
        """Replace all indexed evidence for one paper using index_run_id snapshot switching.

        A new run id is created, data is upserted with that run id, and only after
        all three collections succeed is the new run activated. If anything fails,
        queries continue to see the previously active run. Old runs are cleaned up
        asynchronously after activation.
        """

        if self._paper_service is None:
            # Fallback for callers that do not supply a paper service: old behavior.
            await self.delete_by_paper(paper_id)
            await self.index_chunks(chunks)
            await self.index_entities(entities)
            await self.index_relations(relations)
            return

        # Capture the previous active run before writing the new one, so cleanup
        # can target exactly that run and never accidentally remove data written
        # by concurrent or failed replaces.
        previous_run_id = self._paper_service.get_active_run_id(paper_id)

        # Ensure any stale cleanup from a previous replace finishes before we write
        # the new run, preventing it from deleting data from the upcoming run.
        await self._await_pending_cleanups(paper_id)

        run_id = _generate_run_id()
        await self._index_chunks(chunks, run_id=run_id)
        await self._index_entities(entities, run_id=run_id)
        await self._index_relations(relations, run_id=run_id)

        # Activation is the commit point. Failures before this leave the old run active.
        self._paper_service.set_active_run_id(paper_id, run_id)

        # Best-effort async cleanup of exactly the previous run now that the new
        # run is live. Targeting the explicit previous run id avoids deleting data
        # belonging to a newer failed or concurrent replace.
        if previous_run_id:
            task = asyncio.create_task(self._cleanup_run(paper_id, previous_run_id))
            self._pending_cleanups.setdefault(paper_id, set()).add(task)
            task.add_done_callback(lambda _: self._pending_cleanups.get(paper_id, set()).discard(task))

    async def index_chunks(self, chunks: list[PaperChunk]) -> None:
        """Upsert paper text chunks into the chunk collection using the active run id."""

        run_id = self._active_run_id_for_write(chunks[0].paper_id if chunks else "")
        await self._index_chunks(chunks, run_id=run_id)

    async def _index_chunks(self, chunks: list[PaperChunk], *, run_id: str | None) -> None:
        if not chunks:
            return
        documents = [chunk.text for chunk in chunks]
        ids = [_chunk_chroma_id(chunk.paper_id, chunk.chunk_id, run_id) for chunk in chunks]
        metadatas = [
            clean_metadata(
                self._with_run_id(
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
                    },
                    run_id=run_id,
                )
            )
            for chunk in chunks
        ]
        await self._upsert(self._chunk_collection, ids=ids, documents=documents, metadatas=metadatas)

    async def index_entities(self, entities: list[PaperEntity]) -> None:
        """Upsert graph entities into the entity collection using the active run id."""

        run_id = self._active_run_id_for_write(entities[0].paper_id if entities else "")
        await self._index_entities(entities, run_id=run_id)

    async def _index_entities(self, entities: list[PaperEntity], *, run_id: str | None) -> None:
        if not entities:
            return
        documents = [entity.description for entity in entities]
        ids = [_entity_chroma_id(entity.paper_id, entity.entity_id, run_id) for entity in entities]
        metadatas = [
            clean_metadata(
                self._with_run_id(
                    {
                        "paper_id": entity.paper_id,
                        "evidence_type": VectorEvidenceType.ENTITY.value,
                        "entity_id": entity.entity_id,
                        "label": entity.label,
                        "node_type": entity.node_type,
                        "source_span": entity.source_span,
                    },
                    run_id=run_id,
                )
            )
            for entity in entities
        ]
        await self._upsert(self._entity_collection, ids=ids, documents=documents, metadatas=metadatas)

    async def index_relations(self, relations: list[PaperRelation]) -> None:
        """Upsert graph relations into the relation collection using the active run id."""

        run_id = self._active_run_id_for_write(relations[0].paper_id if relations else "")
        await self._index_relations(relations, run_id=run_id)

    async def _index_relations(self, relations: list[PaperRelation], *, run_id: str | None) -> None:
        if not relations:
            return
        documents = [relation.description for relation in relations]
        ids = [_relation_chroma_id(relation.paper_id, relation.relation_id, run_id) for relation in relations]
        metadatas = [
            clean_metadata(
                self._with_run_id(
                    {
                        "paper_id": relation.paper_id,
                        "evidence_type": VectorEvidenceType.RELATION.value,
                        "relation_id": relation.relation_id,
                        "source_id": relation.source_id,
                        "target_id": relation.target_id,
                        "relation_type": relation.relation_type,
                        "rationale": relation.rationale,
                        "source_span": relation.source_span,
                    },
                    run_id=run_id,
                )
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
    ) -> list:
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
    ) -> list:
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
    ) -> list:
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

        where = self._build_where(paper_id, run_id=None)
        await asyncio.gather(
            asyncio.to_thread(partial(self._chunk_collection.delete, where=where)),
            asyncio.to_thread(partial(self._entity_collection.delete, where=where)),
            asyncio.to_thread(partial(self._relation_collection.delete, where=where)),
        )
        if self._paper_service is not None:
            self._paper_service.set_active_run_id(paper_id, "")

    async def exists(self, paper_id: str) -> bool:
        """Return true when a complete active index run exists for the paper.

        When a paper service is supplied, an active run id must be set and all
        three collections must contain records for that run. This prevents a
        partial (failed) re-index from being reported as available.
        """

        if self._paper_service is not None:
            active_run_id = self._paper_service.get_active_run_id(paper_id)
            if not active_run_id:
                return False
            where = self._build_where(paper_id, run_id=active_run_id)
            results = await asyncio.gather(
                asyncio.to_thread(partial(self._chunk_collection.get, where=where, limit=1, include=[])),
                asyncio.to_thread(partial(self._entity_collection.get, where=where, limit=1, include=[])),
                asyncio.to_thread(partial(self._relation_collection.get, where=where, limit=1, include=[])),
            )
            return all(_result_has_ids(result) for result in results)

        # Legacy fallback for callers without a paper service: any evidence counts.
        where = self._build_where(paper_id, run_id=None)
        results = await asyncio.gather(
            asyncio.to_thread(partial(self._chunk_collection.get, where=where, limit=1, include=[])),
            asyncio.to_thread(partial(self._entity_collection.get, where=where, limit=1, include=[])),
            asyncio.to_thread(partial(self._relation_collection.get, where=where, limit=1, include=[])),
        )
        return any(_result_has_ids(result) for result in results)

    def _active_run_id_for_write(self, paper_id: str) -> str | None:
        """Return the active run id for incremental writes, or None when unmanaged."""

        if self._paper_service is None or not paper_id:
            return None
        return self._paper_service.get_active_run_id(paper_id)

    def _with_run_id(self, metadata: RawMetadata, *, run_id: str | None) -> RawMetadata:
        """Attach index_run_id to metadata when run-aware indexing is enabled."""

        if run_id:
            metadata = dict(metadata)
            metadata["index_run_id"] = run_id
        return metadata

    def _build_where(
        self,
        paper_id: str,
        *,
        run_id: str | None,
    ) -> ChromaWhere:
        """Build a ChromaDB where clause that optionally filters by active run id."""

        paper_clause: ChromaWhere = {"paper_id": paper_id}
        if self._paper_service is None or run_id is None:
            return paper_clause
        return {"$and": [paper_clause, {"index_run_id": run_id}]}

    async def _await_pending_cleanups(self, paper_id: str) -> None:
        """Wait for any in-flight cleanup tasks for this paper to finish."""

        pending = self._pending_cleanups.pop(paper_id, set())
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _cleanup_run(self, paper_id: str, run_id: str) -> None:
        """Best-effort deletion of all indexed evidence for a specific run id."""

        where: ChromaWhere = {
            "$and": [
                {"paper_id": paper_id},
                {"index_run_id": run_id},
            ]
        }
        await asyncio.gather(
            asyncio.to_thread(partial(self._chunk_collection.delete, where=where)),
            asyncio.to_thread(partial(self._entity_collection.delete, where=where)),
            asyncio.to_thread(partial(self._relation_collection.delete, where=where)),
        )

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
    ) -> list:
        if not query_text.strip() or top_k <= 0:
            return []

        query_embeddings = await self._embedding_client.embed_texts([query_text])
        active_run_id = self._paper_service.get_active_run_id(paper_id) if paper_id and self._paper_service else None
        where: ChromaWhere | None = self._build_where(paper_id, run_id=active_run_id) if paper_id is not None else None
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
