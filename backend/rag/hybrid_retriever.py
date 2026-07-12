"""Hybrid graph + vector retrieval for multi-scale QA (V2 §4.2)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from backend.graph.query import GraphQuery
from backend.rag.exceptions import VectorStoreUnavailableError
from backend.rag.models import (
    QuestionScale,
    RetrievalContext,
    RetrievedChunk,
    RetrievedEntity,
    RetrievedRelation,
)
from backend.rag.protocols import VectorStoreProtocol

if TYPE_CHECKING:
    from backend.schemas.graph import UnifiedPaperGraph

logger = logging.getLogger(__name__)

_hybrid_retriever_singleton: HybridRetriever | None = None


class HybridRetriever:
    """Retrieve graph subgraph and vector evidence for one QA turn."""

    def __init__(
        self,
        graph_query: GraphQuery | None = None,
        vector_store: VectorStoreProtocol | None = None,
    ) -> None:
        self._graph_query = graph_query or GraphQuery()
        self._vector_store = vector_store

    @property
    def vector_store(self) -> VectorStoreProtocol | None:
        """Bound vector store for L2 chunk preview lookup and retrieval."""
        return self._vector_store

    def compute_subgraph(self, graph: UnifiedPaperGraph, question: str) -> dict:
        """Return the graph subgraph used for Prompt ``{nodes}/{edges}`` injection."""
        return self._graph_query.subgraph_for_question(graph, question)

    async def retrieve(
        self,
        paper_id: str,
        question: str,
        graph: UnifiedPaperGraph,
        *,
        scale: QuestionScale,
        query_transform: Callable[[str], str] | None = None,
        query_embedding: list[float] | None = None,
        top_k: int | None = None,
        subgraph: dict | None = None,
    ) -> RetrievalContext:
        """Build a ``RetrievalContext`` for ``qa_stream()`` prompt injection.

        Pipeline:
            GraphQuery subgraph (A 尺度, written to RC.nodes/edges) → optional vector
            Top-K (B 尺度) → ``RetrievalContext``.

        ``QaEngine`` treats the returned RC as the single source of truth: when
        ``nodes`` or ``edges`` are populated it formats Prompt ``{nodes}/{edges}``
        from RC directly without a second GraphQuery call.

        Args:
            query_transform: Optional HyDE hook to rewrite *question* before embedding.
            query_embedding: Optional pre-computed embedding for HyDE callers.
            subgraph: Optional pre-computed subgraph to avoid duplicate GraphQuery work
                during timeout / vector-store fallback in ``qa_retrieval``.
        """
        resolved_subgraph = subgraph if subgraph is not None else self.compute_subgraph(graph, question)
        entities: list[RetrievedEntity] = []
        relations: list[RetrievedRelation] = []
        chunks: list[RetrievedChunk] = []

        if scale != QuestionScale.SUMMARY:
            entities, relations, chunks = await self._retrieve_vectors(
                paper_id,
                question,
                query_transform=query_transform,
                query_embedding=query_embedding,
                top_k=top_k,
            )

        return RetrievalContext(
            nodes=resolved_subgraph.get("nodes", []),
            edges=resolved_subgraph.get("edges", []),
            entities=entities,
            relations=relations,
            chunks=chunks,
            scale=scale,
        )

    def build_graph_only_context(
        self,
        paper_id: str,
        question: str,
        graph: UnifiedPaperGraph,
        *,
        scale: QuestionScale,
        subgraph: dict | None = None,
    ) -> RetrievalContext:
        """Graph-only fallback when vector retrieval is unavailable or timed out."""
        _ = paper_id
        resolved_subgraph = subgraph if subgraph is not None else self.compute_subgraph(graph, question)
        return RetrievalContext(
            nodes=resolved_subgraph.get("nodes", []),
            edges=resolved_subgraph.get("edges", []),
            entities=[],
            relations=[],
            chunks=[],
            scale=scale,
        )

    async def _retrieve_vectors(
        self,
        paper_id: str,
        question: str,
        *,
        query_transform: Callable[[str], str] | None,
        query_embedding: list[float] | None,
        top_k: int | None = None,
    ) -> tuple[list[RetrievedEntity], list[RetrievedRelation], list[RetrievedChunk]]:
        if self._vector_store is None:
            return [], [], []

        index_ready = await self._vector_store_index_ready(paper_id)
        if not index_ready:
            logger.info("hybrid_retriever skip vectors: no index for paper_id=%s", paper_id)
            return [], [], []

        query_text = (query_transform(question) if query_transform else question).strip()
        if not query_text:
            return [], [], []

        try:
            return await asyncio.gather(
                self._vector_store.query_entities(
                    query_text,
                    paper_id=paper_id,
                    top_k=top_k,
                    query_embedding=query_embedding,
                ),
                self._vector_store.query_relations(
                    query_text,
                    paper_id=paper_id,
                    top_k=top_k,
                    query_embedding=query_embedding,
                ),
                self._vector_store.query_chunks(
                    query_text,
                    paper_id=paper_id,
                    top_k=top_k,
                    query_embedding=query_embedding,
                ),
            )
        except VectorStoreUnavailableError:
            raise
        except Exception as exc:
            raise VectorStoreUnavailableError(
                f"vector retrieval failed for paper_id={paper_id}",
                paper_id=paper_id,
                cause=exc,
            ) from exc

    async def _vector_store_index_ready(self, paper_id: str) -> bool:
        try:
            return await self._vector_store.exists(paper_id)  # type: ignore[union-attr]
        except VectorStoreUnavailableError:
            raise
        except Exception as exc:
            raise VectorStoreUnavailableError(
                f"vector index check failed for paper_id={paper_id}",
                paper_id=paper_id,
                cause=exc,
            ) from exc


def create_hybrid_retriever(vector_store: VectorStoreProtocol | None = None) -> HybridRetriever:
    """Construct a HybridRetriever; default wiring uses the shared VectorStore."""
    if vector_store is None:
        from backend.rag.vector_store import VectorStore
        from backend.services.paper_service import get_paper_service

        vector_store = VectorStore(paper_service=get_paper_service())
    return HybridRetriever(vector_store=vector_store)


def bind_hybrid_retriever(retriever: HybridRetriever) -> None:
    """Register the process-wide HybridRetriever (app lifespan / tests)."""
    global _hybrid_retriever_singleton
    _hybrid_retriever_singleton = retriever


def reset_hybrid_retriever() -> None:
    """Clear the process-wide HybridRetriever singleton."""
    global _hybrid_retriever_singleton
    _hybrid_retriever_singleton = None


def get_hybrid_retriever() -> HybridRetriever:
    """Return the app-bound HybridRetriever, creating one if unset."""
    global _hybrid_retriever_singleton
    if _hybrid_retriever_singleton is None:
        _hybrid_retriever_singleton = create_hybrid_retriever()
    return _hybrid_retriever_singleton
