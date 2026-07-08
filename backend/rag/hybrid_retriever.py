"""Hybrid graph + vector retriever for V2 paper QA."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from backend.graph.query import GraphQuery
from backend.rag.models import QuestionScale, RetrievalContext, RetrievedChunk, RetrievedEntity, RetrievedRelation
from backend.rag.qa_router import detect_question_scale
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph


class VectorStoreProtocol(Protocol):
    """Vector retrieval interface consumed by ``HybridRetriever``."""

    async def query_chunks(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        """Return chunk evidence scoped to one paper."""
        ...

    async def query_entities(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedEntity]:
        """Return entity evidence scoped to one paper."""
        ...

    async def query_relations(
        self,
        query_text: str,
        *,
        paper_id: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedRelation]:
        """Return relation evidence scoped to one paper."""
        ...


class HybridRetriever:
    """Retrieve graph subgraph context plus vector evidence for a single paper."""

    def __init__(
        self,
        graph_query: GraphQuery | None = None,
        vector_store: VectorStoreProtocol | None = None,
    ) -> None:
        self._graph_query = graph_query or GraphQuery()
        self._vector_store = vector_store or VectorStore()

    async def retrieve(
        self,
        paper_id: str,
        question: str,
        graph: UnifiedPaperGraph,
        *,
        scale: QuestionScale | None = None,
        query_transform: Callable[[str], str] | None = None,
        query_embedding: list[float] | None = None,
    ) -> RetrievalContext:
        """Return graph subgraph plus retrieved entities, relations, and chunks.

        ``query_transform`` and ``query_embedding`` are HyDE extension points.
        A future HyDE implementation can rewrite the question or precompute the
        embedding while this retriever keeps the same downstream contract.
        """

        if not isinstance(paper_id, str) or not paper_id.strip():
            raise ValueError("paper_id must be a non-empty string for single-paper hybrid retrieval.")

        resolved_scale = scale or detect_question_scale(question)
        if resolved_scale == QuestionScale.CROSS_PAPER:
            raise ValueError("cross-paper questions should be routed to Patrol rather than single-paper QA.")

        subgraph = self._graph_query.subgraph_for_question(graph, question)
        if resolved_scale == QuestionScale.SKELETON:
            return RetrievalContext(
                nodes=list(subgraph.get("nodes", [])),
                edges=list(subgraph.get("edges", [])),
                scale=resolved_scale,
            )

        retrieval_query = query_transform(question) if query_transform is not None else question
        entities, relations, chunks = await asyncio.gather(
            self._vector_store.query_entities(
                retrieval_query,
                paper_id=paper_id,
                query_embedding=query_embedding,
            ),
            self._vector_store.query_relations(
                retrieval_query,
                paper_id=paper_id,
                query_embedding=query_embedding,
            ),
            self._vector_store.query_chunks(
                retrieval_query,
                paper_id=paper_id,
                query_embedding=query_embedding,
            ),
        )
        nodes, edges = _merge_graph_context(graph, subgraph, entities, relations)
        return RetrievalContext(
            nodes=nodes,
            edges=edges,
            entities=entities,
            relations=relations,
            chunks=chunks,
            scale=resolved_scale,
        )


def _merge_graph_context(
    graph: UnifiedPaperGraph,
    subgraph: dict,
    entities: list[RetrievedEntity],
    relations: list[RetrievedRelation],
) -> tuple[list[dict], list[dict]]:
    node_ids = _ids_from_subgraph(subgraph.get("nodes", []), key="id")
    edge_ids = _ids_from_subgraph(subgraph.get("edges", []), key="id")

    node_ids.update(entity.entity_id for entity in entities)
    for relation in relations:
        edge_ids.add(relation.relation_id)
        node_ids.add(relation.source_id)
        node_ids.add(relation.target_id)

    nodes = [_dump_node(node) for node in graph.nodes if node.id in node_ids]
    edges = [_dump_edge(edge) for edge in graph.edges if edge.id in edge_ids]
    return nodes, edges


def _ids_from_subgraph(items: object, *, key: str) -> set[str]:
    if not isinstance(items, list):
        return set()
    ids: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            raw_id = item.get(key)
            if isinstance(raw_id, str) and raw_id:
                ids.add(raw_id)
    return ids


def _dump_node(node: GraphNode) -> dict:
    return node.model_dump()


def _dump_edge(edge: GraphEdge) -> dict:
    return edge.model_dump()
