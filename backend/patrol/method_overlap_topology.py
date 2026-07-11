"""Lightweight topology resonance filter for method_overlap semantic soft path (Plan C).

Uses 1-hop neighbors from the local ``UnifiedPaperGraph`` edge list (same adjacency
model as ``GraphQuery``) to reject embedding false positives that lack shared
scientific context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.patrol.similarity import cosine_similarity, normalize_label
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph

if TYPE_CHECKING:
    from backend.llm.embeddings import EmbeddingClient

_RESONANCE_NEIGHBOR_TYPES = frozenset(
    {
        NodeType.DATASET,
        NodeType.RESEARCH_QUESTION,
    }
)


def _node_index(graph: UnifiedPaperGraph) -> dict[str, GraphNode]:
    return {node.id: node for node in graph.nodes}


def one_hop_neighbors(graph: UnifiedPaperGraph, node_id: str) -> list[GraphNode]:
    """Return undirected 1-hop neighbors for *node_id*."""
    nodes_by_id = _node_index(graph)
    neighbor_ids: set[str] = set()
    for edge in graph.edges:
        if edge.source == node_id:
            neighbor_ids.add(edge.target)
        elif edge.target == node_id:
            neighbor_ids.add(edge.source)
    return [nodes_by_id[nid] for nid in neighbor_ids if nid in nodes_by_id]


def _typed_neighbors(graph: UnifiedPaperGraph, method_node: GraphNode) -> list[GraphNode]:
    return [
        neighbor for neighbor in one_hop_neighbors(graph, method_node.id) if neighbor.type in _RESONANCE_NEIGHBOR_TYPES
    ]


def _literal_label_intersection(left_nodes: list[GraphNode], right_nodes: list[GraphNode]) -> bool:
    if not left_nodes or not right_nodes:
        return False
    left_labels = {normalize_label(node.label) for node in left_nodes}
    right_labels = {normalize_label(node.label) for node in right_nodes}
    return bool(left_labels & right_labels)


def _dataset_resonance(
    left_graph: UnifiedPaperGraph,
    right_graph: UnifiedPaperGraph,
    left_method: GraphNode,
    right_method: GraphNode,
) -> bool:
    left_datasets = [node for node in _typed_neighbors(left_graph, left_method) if node.type == NodeType.DATASET]
    right_datasets = [node for node in _typed_neighbors(right_graph, right_method) if node.type == NodeType.DATASET]
    return _literal_label_intersection(left_datasets, right_datasets)


def _research_question_literal_resonance(
    left_graph: UnifiedPaperGraph,
    right_graph: UnifiedPaperGraph,
    left_method: GraphNode,
    right_method: GraphNode,
) -> bool:
    left_questions = [
        node for node in _typed_neighbors(left_graph, left_method) if node.type == NodeType.RESEARCH_QUESTION
    ]
    right_questions = [
        node for node in _typed_neighbors(right_graph, right_method) if node.type == NodeType.RESEARCH_QUESTION
    ]
    return _literal_label_intersection(left_questions, right_questions)


async def _research_question_semantic_resonance(
    left_graph: UnifiedPaperGraph,
    right_graph: UnifiedPaperGraph,
    left_method: GraphNode,
    right_method: GraphNode,
    embedding_client: EmbeddingClient,
    rq_threshold: float,
) -> bool:
    left_questions = [
        node for node in _typed_neighbors(left_graph, left_method) if node.type == NodeType.RESEARCH_QUESTION
    ]
    right_questions = [
        node for node in _typed_neighbors(right_graph, right_method) if node.type == NodeType.RESEARCH_QUESTION
    ]
    if not left_questions or not right_questions:
        return False

    left_labels = [node.label for node in left_questions]
    right_labels = [node.label for node in right_questions]
    vectors = await embedding_client.embed_texts(left_labels + right_labels)
    if len(vectors) != len(left_labels) + len(right_labels):
        return False

    left_vectors = vectors[: len(left_labels)]
    right_vectors = vectors[len(left_labels) :]
    for left_vector in left_vectors:
        for right_vector in right_vectors:
            if cosine_similarity(left_vector, right_vector) >= rq_threshold:
                return True
    return False


async def has_topology_resonance(
    left_graph: UnifiedPaperGraph,
    right_graph: UnifiedPaperGraph,
    left_method: GraphNode,
    right_method: GraphNode,
    *,
    embedding_client: EmbeddingClient | None = None,
    rq_threshold: float,
) -> bool:
    """Return True when method pair shares dataset or research-question neighborhood context."""
    if _dataset_resonance(left_graph, right_graph, left_method, right_method):
        return True
    if _research_question_literal_resonance(left_graph, right_graph, left_method, right_method):
        return True
    if embedding_client is None or getattr(embedding_client, "is_mock", False):
        return False
    return await _research_question_semantic_resonance(
        left_graph,
        right_graph,
        left_method,
        right_method,
        embedding_client,
        rq_threshold,
    )
