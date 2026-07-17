# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers and protocols for the ChromaDB-backed VectorStore."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import uuid
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol

from backend.rag.models import (
    PaperChunk,
    PaperEntity,
    PaperRelation,
    RetrievedChunk,
    RetrievedEntity,
    RetrievedRelation,
    VectorEvidenceType,
)

if TYPE_CHECKING:
    from backend.config import Settings
    from backend.rag.models import EmbeddingClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_DIMENSION = 1536


def _query_embedding_validation_issue(
    query_embedding: list[float],
    *,
    expected_dimension: int,
) -> str | None:
    """Return a machine-readable rejection reason, or None when the vector is usable."""
    if not query_embedding:
        return "empty"
    if len(query_embedding) != expected_dimension:
        return f"dimension_mismatch:{len(query_embedding)}!={expected_dimension}"
    if any(not math.isfinite(value) for value in query_embedding):
        return "non_finite"
    return None


async def resolve_query_embeddings(
    query_text: str,
    query_embedding: list[float] | None,
    embedding_client: EmbeddingClientProtocol,
    *,
    expected_dimension: int = DEFAULT_EMBEDDING_DIMENSION,
) -> list[list[float]]:
    """Use a pre-computed HyDE vector or embed *query_text* on demand.

    Invalid ``query_embedding`` values (empty, wrong dimension, NaN/Inf) fall back
    to ``embed_texts`` so Chroma never receives malformed vectors.
    """
    if query_embedding is not None:
        issue = _query_embedding_validation_issue(
            query_embedding,
            expected_dimension=expected_dimension,
        )
        if issue is not None:
            logger.warning(
                "query_embedding_invalid_fallback_to_embed_text",
                extra={"reason": issue, "query_text_len": len(query_text)},
            )
            return await embedding_client.embed_texts([query_text])
        return [query_embedding]
    return await embedding_client.embed_texts([query_text])


async def query_evidence_collection(
    collection: CollectionProtocol,
    embedding_client: EmbeddingClientProtocol,
    query_text: str,
    *,
    evidence_type: VectorEvidenceType,
    paper_id: str,
    top_k: int,
    query_embedding: list[float] | None,
    where: ChromaWhere,
    expected_embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION,
) -> list[RetrievedChunk | RetrievedEntity | RetrievedRelation]:
    """Run a scoped Chroma query and parse typed evidence rows."""
    if not isinstance(paper_id, str) or not paper_id.strip():
        raise ValueError("单篇 QA 路径下严禁泄露全库检索权限：paper_id 必须是非空字符串")
    if not query_text.strip() or top_k <= 0:
        return []

    query_embeddings = await resolve_query_embeddings(
        query_text,
        query_embedding,
        embedding_client,
        expected_dimension=expected_embedding_dimension,
    )
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


async def _embed_in_batches(
    documents: list[str],
    *,
    embedding_client: EmbeddingClientProtocol,
    batch_size: int,
) -> list[list[float]]:
    """Embed documents in configurable batches to avoid API token/throughput limits."""

    if len(documents) <= batch_size:
        return await embedding_client.embed_texts(documents)

    embeddings: list[list[float]] = []
    for index in range(0, len(documents), batch_size):
        batch = documents[index : index + batch_size]
        batch_embeddings = await embedding_client.embed_texts(batch)
        embeddings.extend(batch_embeddings)
    return embeddings


ChromaMetadataValue = str | int | float | bool
ChromaMetadata = dict[str, ChromaMetadataValue]
RawMetadata = dict[str, Any]
ChromaWhereClause = dict[str, Any]
ChromaWhere = dict[str, Any]


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


def clean_metadata(metadata: RawMetadata) -> ChromaMetadata:
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


def _generate_run_id() -> str:
    """Generate a unique, time-ordered RAG index run identifier."""

    return f"run_{datetime.now(UTC).timestamp():.6f}_{uuid.uuid4().hex[:8]}"


def _chunk_chroma_id(paper_id: str, chunk_id: str, run_id: str | None) -> str:
    if run_id:
        return f"{paper_id}:chunk:{run_id}:{chunk_id}"
    return chunk_id


def _entity_chroma_id(paper_id: str, entity_id: str, run_id: str | None = None) -> str:
    if run_id:
        return f"{paper_id}:entity:{run_id}:{entity_id}"
    return f"{paper_id}:entity:{entity_id}"


def _relation_chroma_id(paper_id: str, relation_id: str, run_id: str | None = None) -> str:
    if run_id:
        return f"{paper_id}:relation:{run_id}:{relation_id}"
    return f"{paper_id}:relation:{relation_id}"


def _persistent_chroma_client(path: str) -> Any:
    """Create a local persistent Chroma client."""
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("chromadb is required for VectorStore; install project dependencies first.") from exc
    # PersistentClient returns a concrete ClientAPI implementation, but pyright
    # cannot infer the return type from the dynamic chromadb package.
    return chromadb.PersistentClient(path=path)  # type: ignore[no-any-return]


def _default_embedding_client(settings: Settings | None) -> EmbeddingClientProtocol:
    if settings is not None:
        from backend.llm.embeddings import EmbeddingClient

        return EmbeddingClient(settings)

    from backend.llm.embeddings import get_embedding_client

    return get_embedding_client()


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _is_usable_query_row(*, result_id: Any, document: Any, paper_id: str) -> bool:
    """Drop stale Chroma hits that can appear during concurrent delete/reindex races."""
    if not str(result_id).strip():
        return False
    if not paper_id.strip():
        return False
    if document is None:
        return False
    text = str(document).strip()
    return bool(text) and text != "None"


def _parse_query_results(
    raw_result: dict[str, Any],
    *,
    evidence_type: VectorEvidenceType,
) -> list[RetrievedChunk | RetrievedEntity | RetrievedRelation]:
    ids = _first_query_batch(raw_result.get("ids"))
    documents = _first_query_batch(raw_result.get("documents"))
    metadatas = _first_query_batch(raw_result.get("metadatas"))
    distances = _first_query_batch(raw_result.get("distances"))

    results: list[RetrievedChunk | RetrievedEntity | RetrievedRelation] = []
    for index, result_id in enumerate(ids):
        raw_metadata = _item_at(metadatas, index, default={}) or {}
        metadata = clean_metadata(raw_metadata)
        document = _item_at(documents, index, default=None)
        paper_id = str(metadata.get("paper_id", ""))
        if not _is_usable_query_row(result_id=result_id, document=document, paper_id=paper_id):
            continue
        text = str(document)
        distance = _item_at(distances, index, default=None)
        parsed_distance = float(distance) if isinstance(distance, int | float) else None

        if evidence_type == VectorEvidenceType.CHUNK:
            results.append(
                RetrievedChunk(
                    id=str(result_id),
                    paper_id=paper_id,
                    text=text,
                    distance=parsed_distance,
                    chunk_id=str(metadata.get("chunk_id", result_id)),
                    section=_optional_str(metadata.get("section")),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    source=str(metadata.get("source", "pymupdf")),
                    char_start=int(metadata.get("char_start", 0)),
                    char_end=int(metadata.get("char_end", 0)),
                    page_start=_optional_int(metadata.get("page_start")),
                    page_end=_optional_int(metadata.get("page_end")),
                )
            )
        elif evidence_type == VectorEvidenceType.ENTITY:
            results.append(
                RetrievedEntity(
                    id=str(result_id),
                    paper_id=paper_id,
                    text=text,
                    distance=parsed_distance,
                    entity_id=str(metadata.get("entity_id", result_id)),
                    label=str(metadata.get("label", "")),
                    node_type=str(metadata.get("node_type", "")),
                    source_span=_optional_str(metadata.get("source_span")),
                )
            )
        else:
            results.append(
                RetrievedRelation(
                    id=str(result_id),
                    paper_id=paper_id,
                    text=text,
                    distance=parsed_distance,
                    relation_id=str(metadata.get("relation_id", result_id)),
                    source_id=str(metadata.get("source_id", "")),
                    target_id=str(metadata.get("target_id", "")),
                    relation_type=str(metadata.get("relation_type", "")),
                    rationale=_optional_str(metadata.get("rationale")),
                    source_span=_optional_str(metadata.get("source_span")),
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


def _validate_evidence_paper_ids(
    paper_id: str,
    chunks: list[PaperChunk],
    entities: list[PaperEntity],
    relations: list[PaperRelation],
) -> None:
    """Ensure every evidence item belongs to the target paper.

    Cross-paper indexing is a data-poisoning risk; reject it eagerly.
    """

    for chunk in chunks:
        if chunk.paper_id != paper_id:
            raise ValueError(f"chunk paper_id mismatch: expected {paper_id!r}, got {chunk.paper_id!r}")
    for entity in entities:
        if entity.paper_id != paper_id:
            raise ValueError(f"entity paper_id mismatch: expected {paper_id!r}, got {entity.paper_id!r}")
    for relation in relations:
        if relation.paper_id != paper_id:
            raise ValueError(f"relation paper_id mismatch: expected {paper_id!r}, got {relation.paper_id!r}")
