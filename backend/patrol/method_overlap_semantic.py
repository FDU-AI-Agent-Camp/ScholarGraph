"""Semantic overlap helpers for method_overlap patrol logic."""

from __future__ import annotations

import numpy as np

from backend.config import Settings
from backend.llm.embeddings import EmbeddingClient
from backend.patrol.method_overlap_topology import has_topology_resonance
from backend.patrol.overlap_anchor import _OverlapAnchor
from backend.patrol.similarity import cosine_similarity_matrix
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.patrol import OverlapType


def _embed_text_for_node(node: GraphNode) -> str:
    """Build a single embedding text from a node's label and description."""
    parts = [node.label]
    description = (node.data or {}).get("description")
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    return " ".join(parts)


async def find_semantic_method_overlap(
    left_graph: UnifiedPaperGraph,
    right_graph: UnifiedPaperGraph,
    left_methods: list[GraphNode],
    right_methods: list[GraphNode],
    embedding_client: EmbeddingClient,
    threshold: float,
    max_matrix_size: int,
    *,
    settings: Settings,
) -> _OverlapAnchor | None:
    """Find the strongest topology-validated semantic method overlap across two papers.

    Pipeline:
    1. Build cosine-similarity matrix on ``label + description``.
    2. Collect candidate pairs with score >= *threshold*, highest first.
    3. Apply 1-hop neighborhood resonance filter (Dataset / ResearchQuestion).
    4. Return the first surviving pair, or ``None`` when all candidates are noise.
    """
    if not left_methods or not right_methods:
        return None

    # Mock embeddings are deterministic but not semantically meaningful, so skip
    # the soft path to avoid false positives in test/local mock runs.
    if getattr(embedding_client, "is_mock", False):
        return None

    matrix_size = len(left_methods) * len(right_methods)
    if matrix_size > max_matrix_size:
        return None

    texts = [_embed_text_for_node(node) for node in left_methods + right_methods]
    vectors = await embedding_client.embed_texts(texts)
    if len(vectors) != len(texts):
        return None

    split_at = len(left_methods)
    similarity = cosine_similarity_matrix(vectors[:split_at], vectors[split_at:])
    if similarity.size == 0:
        return None

    candidate_indices = [
        np.unravel_index(index, similarity.shape)
        for index in np.argsort(similarity, axis=None)[::-1]
        if float(similarity[np.unravel_index(index, similarity.shape)]) >= threshold
    ]
    for left_idx, right_idx in candidate_indices:
        left_method = left_methods[left_idx]
        right_method = right_methods[right_idx]
        if not await has_topology_resonance(
            left_graph,
            right_graph,
            left_method,
            right_method,
            embedding_client=embedding_client,
            settings=settings,
        ):
            continue
        return _OverlapAnchor(
            left_node=left_method,
            right_node=right_method,
            overlap_kind=OverlapType.METHOD,
            match_type="semantic",
            overlap_score=float(similarity[left_idx, right_idx]),
        )
    return None
