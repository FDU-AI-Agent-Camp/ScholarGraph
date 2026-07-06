"""Event-facing RAG indexing entry points."""

from __future__ import annotations

import logging

from backend.rag.chunking import chunk_text
from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import UnifiedPaperGraph
from backend.services.paper_service import get_paper_service

logger = logging.getLogger(__name__)

RAG_INDEX_WARNING_CODE = "rag_index_failed"


async def index_paper_for_rag(
    paper_id: str,
    *,
    full_text: str,
    graph: UnifiedPaperGraph,
    vector_store: VectorStore | None = None,
    suppress_errors: bool = True,
) -> bool:
    """Build or replace the RAG vector index for one finalized paper."""

    if not isinstance(paper_id, str) or not paper_id.strip():
        raise ValueError("paper_id must be a non-empty string")
    if graph.paper_id != paper_id:
        raise ValueError(f"graph.paper_id ({graph.paper_id!r}) does not match paper_id ({paper_id!r})")

    store = vector_store or VectorStore()
    try:
        from backend.config import get_settings

        settings = get_settings()
        chunks = chunk_text(
            paper_id,
            full_text,
            chunk_size_chars=settings.rag_chunk_size_chars,
            chunk_overlap_ratio=settings.rag_chunk_overlap_ratio,
            min_chunk_chars=settings.rag_chunk_min_chunk_chars,
            min_soft_boundary_window_chars=settings.rag_chunk_min_soft_boundary_window_chars,
            include_references=settings.rag_chunk_include_references,
        )
        entities = graph_to_entities(paper_id, graph)
        relations = graph_to_relations(paper_id, graph)
        await store.replace_paper_index(
            paper_id,
            chunks=chunks,
            entities=entities,
            relations=relations,
        )
    except Exception as exc:
        exc_type_name = type(exc).__name__
        exc_msg = str(exc)

        # Structured logging for ELK/Loki/Datadog alerting.
        logger.exception(
            RAG_INDEX_WARNING_CODE,
            extra={
                "paper_id": paper_id,
                "exc_type": exc_type_name,
                "exc_msg": exc_msg,
            },
        )

        # Surface the warning in the paper status so users/admins can inspect it.
        _record_index_warning(paper_id, exc_type_name, exc_msg)

        if not suppress_errors:
            raise
        return False
    return True


def _record_index_warning(paper_id: str, exc_type_name: str, exc_msg: str) -> None:
    """Persist a machine-readable RAG index warning on the paper status snapshot.

    The warning code itself is a fixed machine code so frontends can map it
    reliably. Detailed error context (exception type and message) is already
    captured by the structured logger.exception() call in index_paper_for_rag.
    """

    try:
        get_paper_service().record_extract_warnings(paper_id, [RAG_INDEX_WARNING_CODE])
    except Exception:
        # If the status service is unavailable, do not let the warning write
        # hide the original RAG indexing failure.
        logger.exception("failed_to_record_rag_index_warning", extra={"paper_id": paper_id})
