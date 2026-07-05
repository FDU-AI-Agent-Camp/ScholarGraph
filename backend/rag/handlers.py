"""Event-facing RAG indexing entry points."""

from __future__ import annotations

import logging

from backend.rag.chunking import chunk_text
from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import UnifiedPaperGraph

logger = logging.getLogger(__name__)


async def index_paper_for_rag(
    paper_id: str,
    *,
    full_text: str,
    graph: UnifiedPaperGraph,
    vector_store: VectorStore | None = None,
    suppress_errors: bool = True,
) -> bool:
    """Build or replace the RAG vector index for one finalized paper."""

    store = vector_store or VectorStore()
    try:
        from backend.config import get_settings

        settings = get_settings()
        chunks = chunk_text(
            paper_id,
            full_text,
            chunk_size_chars=settings.rag_chunk_size_chars,
            chunk_overlap_ratio=settings.rag_chunk_overlap_ratio,
        )
        entities = graph_to_entities(paper_id, graph)
        relations = graph_to_relations(paper_id, graph)
        await store.replace_paper_index(
            paper_id,
            chunks=chunks,
            entities=entities,
            relations=relations,
        )
    except Exception:
        logger.exception("rag_index_failed", extra={"paper_id": paper_id})
        if not suppress_errors:
            raise
        return False
    return True
