"""Shared QA retrieval-context builder for HTTP routes and benchmarks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.rag.exceptions import VectorStoreUnavailableError
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
VECTOR_STORE_UNAVAILABLE_CODE = "vector_store_unavailable"
VECTOR_STORE_UNAVAILABLE_MESSAGE = "向量库连接异常，已自动降级为纯图谱检索模式"
RAG_INDEX_NOT_READY_CODE = "RAG_INDEX_NOT_READY"
RAG_INDEX_NOT_READY_MESSAGE = (
    "当前原文向量索引未就绪，已安全退化为纯图谱子图推理。回答可生成，但暂无法提供精确页码与高亮文本块引用。"
)
VECTOR_RETRIEVAL_WARNING_SOURCE = "vector_store"


def _vector_retrieval_warning(*, code: str, message: str) -> dict[str, str]:
    """SSE warning payload shared by timeout and vector-store outage fallbacks."""
    return {
        "code": code,
        "message": message,
        "source": VECTOR_RETRIEVAL_WARNING_SOURCE,
    }


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
    resolved_timeout = timeout_seconds if timeout_seconds is not None else get_settings().qa_retrieval_timeout_seconds
    subgraph = retriever.compute_subgraph(graph, question)

    try:
        context = await asyncio.wait_for(
            retriever.retrieve(
                paper_id,
                question,
                graph,
                scale=scale,
                top_k=top_k,
                subgraph=subgraph,
            ),
            timeout=resolved_timeout,
        )
        if not context.metadata.index_ready:
            logger.info(
                "qa_retrieval_index_not_ready paper_id=%s scale=%s reason=%s — graph-only synthesis",
                paper_id,
                scale.value,
                context.metadata.missing_reason,
            )
            return RetrievalBuildResult(
                context=context,
                warning_event=_vector_retrieval_warning(
                    code=RAG_INDEX_NOT_READY_CODE,
                    message=RAG_INDEX_NOT_READY_MESSAGE,
                ),
            )
        return RetrievalBuildResult(context=context)
    except VectorStoreUnavailableError as exc:
        logger.warning(
            "qa_retrieval_vector_store_unavailable paper_id=%s scale=%s — graph-only fallback",
            paper_id,
            scale.value,
            exc_info=exc.cause or exc,
        )
        context = retriever.build_graph_only_context(
            paper_id,
            question,
            graph,
            scale=scale,
            subgraph=subgraph,
        )
        return RetrievalBuildResult(
            context=context,
            warning_event=_vector_retrieval_warning(
                code=VECTOR_STORE_UNAVAILABLE_CODE,
                message=VECTOR_STORE_UNAVAILABLE_MESSAGE,
            ),
        )
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
            subgraph=subgraph,
        )
        return RetrievalBuildResult(
            context=context,
            warning_event=_vector_retrieval_warning(
                code=VECTOR_RETRIEVAL_TIMEOUT_CODE,
                message=VECTOR_RETRIEVAL_TIMEOUT_MESSAGE,
            ),
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

    scale = detect_question_scale(
        question,
        paradigm=graph.paradigm,
        current_paper_context={"paper_id": paper_id},
    )
    if scale == QuestionScale.CROSS_PAPER:
        return None
    return graph, scale
