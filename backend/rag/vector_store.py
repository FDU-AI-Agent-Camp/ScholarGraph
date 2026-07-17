# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""ChromaDB-backed vector store for RAG chunks, entities, and relations.

Run-id snapshot replace + generation-guard activation live in
``vector_store_replace.ReplacePaperIndexMixin`` (P13; keeps this module under D-12).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from functools import partial
from typing import TYPE_CHECKING, cast

from backend.rag.models import (
    EmbeddingClientProtocol,
    PaperChunk,
    PaperEntity,
    PaperRelation,
    RetrievedChunk,
    RetrievedEntity,
    RetrievedRelation,
    VectorEvidenceType,
)
from backend.rag.protocols import VectorStoreProtocol
from backend.rag.vector_store_chunk_text import ChunkTextLookupMixin
from backend.rag.vector_store_replace import (
    GENERATION_GUARD_LOG_PREFIX,
    ObsoleteGenerationWarning,
    ReplacePaperIndexMixin,
)
from backend.rag.vector_store_utils import (
    DEFAULT_EMBEDDING_DIMENSION,
    ChromaMetadata,
    ChromaWhere,
    CollectionProtocol,
    RawMetadata,
    _chunk_chroma_id,
    _default_embedding_client,
    _embed_in_batches,
    _entity_chroma_id,
    _persistent_chroma_client,
    _relation_chroma_id,
    _result_has_ids,
    clean_metadata,
    query_evidence_collection,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from backend.config import Settings
    from backend.services.paper_service import PaperService

__all__ = [
    "ChromaMetadata",
    "ChromaWhere",
    "CollectionProtocol",
    "GENERATION_GUARD_LOG_PREFIX",
    "ObsoleteGenerationWarning",
    "VectorStore",
    "clean_metadata",
]


class VectorStore(ChunkTextLookupMixin, ReplacePaperIndexMixin):
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
        self._replace_locks: dict[str, asyncio.Lock] = {}
        from backend.config import get_settings

        self._settings = settings or get_settings()
        if chunk_collection is not None and entity_collection is not None and relation_collection is not None:
            self._chunk_collection = chunk_collection
            self._entity_collection = entity_collection
            self._relation_collection = relation_collection
            self._bind_chunk_text_lru()
            return

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
        self._bind_chunk_text_lru()

    async def index_chunks(self, chunks: list[PaperChunk]) -> None:
        """Upsert paper text chunks into the chunk collection using the active run id."""

        run_id = self._active_run_id_for_write(chunks[0].paper_id if chunks else "")
        await self._index_chunks(chunks, run_id=run_id)

    async def _index_chunks(self, chunks: list[PaperChunk], *, run_id: str | None) -> None:
        if not chunks:
            return
        if self._paper_service is not None and not run_id:
            logger.warning(
                "index_chunks_skipped_missing_run_id",
                extra={"paper_id": chunks[0].paper_id, "chunk_count": len(chunks)},
            )
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
        if self._paper_service is not None and not run_id:
            logger.warning(
                "index_entities_skipped_missing_run_id",
                extra={"paper_id": entities[0].paper_id, "entity_count": len(entities)},
            )
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
        if self._paper_service is not None and not run_id:
            logger.warning(
                "index_relations_skipped_missing_run_id",
                extra={"paper_id": relations[0].paper_id, "relation_count": len(relations)},
            )
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

    def _default_top_k(self, evidence_type: VectorEvidenceType) -> int:
        mapping = {
            VectorEvidenceType.CHUNK: "rag_top_k_chunks",
            VectorEvidenceType.ENTITY: "rag_top_k_entities",
            VectorEvidenceType.RELATION: "rag_top_k_relations",
        }
        return getattr(self._settings, mapping[evidence_type], 5)

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        return cast(
            list[RetrievedChunk],
            await self._query(
                self._chunk_collection,
                query_text,
                evidence_type=VectorEvidenceType.CHUNK,
                paper_id=paper_id,
                top_k=top_k,
                query_embedding=query_embedding,
            ),
        )

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedEntity]:
        return cast(
            list[RetrievedEntity],
            await self._query(
                self._entity_collection,
                query_text,
                evidence_type=VectorEvidenceType.ENTITY,
                paper_id=paper_id,
                top_k=top_k,
                query_embedding=query_embedding,
            ),
        )

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedRelation]:
        return cast(
            list[RetrievedRelation],
            await self._query(
                self._relation_collection,
                query_text,
                evidence_type=VectorEvidenceType.RELATION,
                paper_id=paper_id,
                top_k=top_k,
                query_embedding=query_embedding,
            ),
        )

    async def delete_by_paper(self, paper_id: str) -> None:
        """Delete all indexed evidence for one paper from all collections."""
        where = self._build_where(paper_id, run_id=None)
        await asyncio.gather(
            asyncio.to_thread(partial(self._chunk_collection.delete, where=where)),
            asyncio.to_thread(partial(self._entity_collection.delete, where=where)),
            asyncio.to_thread(partial(self._relation_collection.delete, where=where)),
        )
        self.clear_chunk_text_lru()
        if self._paper_service is not None:
            self._paper_service.set_active_run_id(paper_id, None)

    async def exists(self, paper_id: str) -> bool:
        """Return true when a complete active index run exists for the paper.

        When a paper service is supplied, an active run id must be set and at
        least one collection must contain records for that run. Empty evidence
        (no chunks, entities, or relations) is still reported as existing once
        the run has been activated, because a paper with zero RAG evidence is a
        valid outcome.
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
            # A run is complete if it has any evidence, or if all three
            # collections are empty (activated replace with no evidence).
            return any(_result_has_ids(result) for result in results) or all(
                not _result_has_ids(result) for result in results
            )

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
        """Build Chroma where for *paper_id*, optionally constrained to ``index_run_id``.

        Run-aware read callers must pass a non-empty *run_id*; when no active run
        is set they fail-closed before querying so orphan ghosts stay invisible.
        """
        paper_clause: ChromaWhere = {"paper_id": paper_id}
        if self._paper_service is None or run_id is None:
            return paper_clause
        return {"$and": [paper_clause, {"index_run_id": run_id}]}

    async def _await_pending_cleanups(self, paper_id: str) -> None:
        """Wait for any in-flight cleanup tasks for this paper to finish."""

        pending = self._pending_cleanups.pop(paper_id, set())
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def delete_run(self, paper_id: str, run_id: str) -> None:
        """Public best-effort deletion of one index_run_id snapshot (compensating cleanup)."""
        await self._cleanup_run(paper_id, run_id)

    async def delete_by_run_id(self, paper_id: str, run_id: str) -> None:
        """Alias for ``delete_run`` — Wave-2 wipe / orphan compensate API."""
        await self.delete_run(paper_id, run_id)

    async def _cleanup_run_safely(self, paper_id: str, run_id: str) -> None:
        """Best-effort deletion of a partially-written run; logs but never raises."""

        try:
            await self._cleanup_run(paper_id, run_id)
        except Exception:
            logger.exception(
                "orphan_run_cleanup_failed",
                extra={"paper_id": paper_id, "run_id": run_id},
            )

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
        batch_size = getattr(self._settings, "embedding_batch_size", 32)
        embeddings = await _embed_in_batches(
            documents,
            embedding_client=self._embedding_client,
            batch_size=batch_size,
        )
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
        paper_id: str,
        top_k: int | None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk | RetrievedEntity | RetrievedRelation]:
        resolved_top_k = top_k if top_k is not None else self._default_top_k(evidence_type)
        # Soft isolation: without an active run, late orphan upserts must not surface.
        if self._paper_service is not None:
            active_run_id = self._paper_service.get_active_run_id(paper_id)
            if not active_run_id:
                return []
            where: ChromaWhere = self._build_where(paper_id, run_id=active_run_id)
        else:
            where = self._build_where(paper_id, run_id=None)
        expected_dimension = int(getattr(self._settings, "embedding_dimension", DEFAULT_EMBEDDING_DIMENSION))
        return await query_evidence_collection(
            collection,
            self._embedding_client,
            query_text,
            evidence_type=evidence_type,
            paper_id=paper_id,
            top_k=resolved_top_k,
            query_embedding=query_embedding,
            where=where,
            expected_embedding_dimension=expected_dimension,
        )


_inspect_compliance: VectorStoreProtocol = cast(VectorStore, None)
