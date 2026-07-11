"""Shared QA retrieval-context builder for HTTP routes and benchmarks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.rag.models import QuestionScale, RetrievalContext
from backend.rag.qa_router import detect_question_scale
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import PaperService

if TYPE_CHECKING:
    from backend.rag.hybrid_retriever import HybridRetriever
    from backend.schemas.graph import UnifiedPaperGraph

logger = logging.getLogger(__name__)

VECTOR_RETRIEVAL_TIMEOUT_CODE = "vector_retrieval_timeout"
VECTOR_RETRIEVAL_TIMEOUT_MESSAGE = "向量检索超时，正在使用纯图知识库答题"


@dataclass(frozen=True, slots=True)
class RetrievalBuildResult:
    """Outcome of hybrid retrieval with optional graph-only fallback."""

    context: RetrievalContext | None
    warning_event: dict[str, str] | None = None


async def build_retrieval_context(
    paper_id: str,
    question: str,
    *,
    retriever: HybridRetriever,
    paper_service: PaperService,
    store: GraphStore | None = None,
    top_k: int | None = None,
) -> RetrievalContext | None:
    """Load graph, detect scale, and run ``HybridRetriever.retrieve()``."""
    result = await build_retrieval_context_with_fallback(
        paper_id,
        question,
        retriever=retriever,
        paper_service=paper_service,
        store=store,
        top_k=top_k,
    )
    return result.context


async def build_retrieval_context_with_fallback(
    paper_id: str,
    question: str,
    *,
    retriever: HybridRetriever,
    paper_service: PaperService,
    store: GraphStore | None = None,
    top_k: int | None = None,
    timeout_seconds: float | None = None,
) -> RetrievalBuildResult:
    """Retrieve hybrid context; on timeout degrade to graph-only and emit warning metadata."""
    loaded = await _load_graph_for_retrieval(
        paper_id,
        question,
        paper_service=paper_service,
        store=store,
    )
    if loaded is None:
        return RetrievalBuildResult(context=None)

    graph, scale = loaded
    resolved_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else get_settings().qa_retrieval_timeout_seconds
    )

    try:
        context = await asyncio.wait_for(
            retriever.retrieve(
                paper_id,
                question,
                graph,
                scale=scale,
                top_k=top_k,
            ),
            timeout=resolved_timeout,
        )
        return RetrievalBuildResult(context=context)
    except TimeoutError:
        logger.warning(
            "qa_retrieval_timeout paper_id=%s scale=%s timeout=%.1fs — graph-only fallback",
            paper_id,
            scale.value,
            resolved_timeout,
        )
        context = retriever.build_graph_only_context(
            paper_id,
            question,
            graph,
            scale=scale,
        )
        return RetrievalBuildResult(
            context=context,
            warning_event={
                "code": VECTOR_RETRIEVAL_TIMEOUT_CODE,
                "message": VECTOR_RETRIEVAL_TIMEOUT_MESSAGE,
            },
        )


async def _load_graph_for_retrieval(
    paper_id: str,
    question: str,
    *,
    paper_service: PaperService,
    store: GraphStore | None,
) -> tuple[UnifiedPaperGraph, QuestionScale] | None:
    paper = await paper_service.get_paper(paper_id)
    is_preview = paper.status not in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS}
    if is_preview and not paper.preview_available:
        return None

    graph_store = store or GraphStore()
    graph = graph_store.load(paper_id)
    if graph is None:
        graph = paper_service.get_preview_graph(paper_id)
    if graph is None:
        return None

    scale = detect_question_scale(question, paradigm=graph.paradigm)
    return graph, scale
