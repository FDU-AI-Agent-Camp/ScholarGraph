"""QA orchestration facade for benchmark scripts (HTTP route uses explicit deps)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import TYPE_CHECKING

from backend.graph.store import GraphStore
from backend.services.qa_retrieval import build_retrieval_context_with_fallback

if TYPE_CHECKING:
    from backend.graph.qa import QaEvent
    from backend.llm.client import LlmClient
    from backend.rag.hybrid_retriever import HybridRetriever
    from backend.services.paper_service import PaperService


class QaService:
    """Benchmark-friendly wrapper: retrieve → ``qa_stream()``."""

    def __init__(
        self,
        *,
        store: GraphStore | None = None,
        paper_service: PaperService | None = None,
        hybrid_retriever: HybridRetriever | None = None,
    ) -> None:
        from backend.services.paper_service import get_paper_service

        self._store = store or GraphStore()
        self._paper_service = paper_service or get_paper_service()
        self._hybrid_retriever = hybrid_retriever

    async def stream(
        self,
        paper_id: str,
        question: str,
        *,
        llm: LlmClient | None = None,
        top_k: int | None = None,
    ) -> AsyncIterator[QaEvent]:
        from backend.graph.qa import qa_stream
        from backend.rag.hybrid_retriever import get_hybrid_retriever

        retriever = self._hybrid_retriever or get_hybrid_retriever()
        retrieval_result = await build_retrieval_context_with_fallback(
            paper_id,
            question,
            retriever=retriever,
            paper_service=self._paper_service,
            store=self._store,
            top_k=top_k,
        )
        async for evt in qa_stream(
            paper_id,
            question,
            retrieval_context=retrieval_result.context,
            llm=llm,
        ):
            yield evt


@lru_cache
def get_qa_service() -> QaService:
    return QaService()
