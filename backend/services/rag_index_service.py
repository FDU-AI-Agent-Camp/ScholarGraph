"""Service facade for triggering RAG vector indexing from the workflow graph."""

from __future__ import annotations

import logging
from functools import lru_cache

from backend.config import get_settings
from backend.rag.handlers import index_paper_for_rag
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import UnifiedPaperGraph

logger = logging.getLogger(__name__)

RAG_INDEX_STAGE_MESSAGE = "正在构建 RAG 向量索引"


class RagIndexService:
    """High-level entry point for building or replacing a paper's RAG index."""

    async def index_paper_for_rag_async(
        self,
        paper_id: str,
        *,
        full_text: str,
        graph: UnifiedPaperGraph,
        page_break_offsets: list[int] | None = None,
    ) -> bool:
        """Build the RAG vector index for one finalized paper.

        Returns True when indexing succeeded or was intentionally skipped (mock).
        """

        from backend.services.paper_service import get_paper_service

        settings = get_settings()
        if settings.is_llm_mock:
            logger.info("rag_index_skipped_in_mock_mode", extra={"paper_id": paper_id})
            return True

        logger.info(RAG_INDEX_STAGE_MESSAGE, extra={"paper_id": paper_id})
        vector_store = VectorStore(
            chroma_path=settings.chromadb_path,
            paper_service=get_paper_service(),
        )
        return await index_paper_for_rag(
            paper_id,
            full_text=full_text,
            graph=graph,
            vector_store=vector_store,
            suppress_errors=True,
            page_break_offsets=page_break_offsets,
        )


@lru_cache
def get_rag_index_service() -> RagIndexService:
    return RagIndexService()
