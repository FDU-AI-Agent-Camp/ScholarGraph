"""Shared helpers and protocols for the ChromaDB-backed VectorStore."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from backend.rag.models import VectorEvidenceType, VectorSearchResult

if TYPE_CHECKING:
    from backend.config import Settings
    from backend.rag.models import EmbeddingClientProtocol

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


def _parse_query_results(raw_result: dict[str, Any], *, evidence_type: VectorEvidenceType) -> list[VectorSearchResult]:
    ids = _first_query_batch(raw_result.get("ids"))
    documents = _first_query_batch(raw_result.get("documents"))
    metadatas = _first_query_batch(raw_result.get("metadatas"))
    distances = _first_query_batch(raw_result.get("distances"))

    results: list[VectorSearchResult] = []
    for index, result_id in enumerate(ids):
        raw_metadata = _item_at(metadatas, index, default={}) or {}
        metadata = clean_metadata(raw_metadata)
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
