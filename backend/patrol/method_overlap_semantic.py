"""Semantic overlap helpers for method_overlap patrol logic."""

from __future__ import annotations

import numpy as np

from backend.llm.embeddings import EmbeddingClient
from backend.patrol.overlap_anchor import _OverlapAnchor
from backend.patrol.similarity import cosine_similarity_matrix
from backend.schemas.graph import GraphNode
from backend.schemas.patrol import OverlapType


def _embed_text_for_node(node: GraphNode) -> str:
    """Build a single embedding text from a node's label and description."""
    parts = [node.label]
    description = (node.data or {}).get("description")
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    return " ".join(parts)


async def find_semantic_method_overlap(
    left_methods: list[GraphNode],
    right_methods: list[GraphNode],
    embedding_client: EmbeddingClient,
    threshold: float,
    max_matrix_size: int,
) -> _OverlapAnchor | None:
    """Find the strongest semantic method overlap across two papers.

    Returns the best matching anchor plus the cosine score, or ``None`` when no
    pair exceeds the threshold or the matrix is too large.
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

    best_index = int(np.argmax(similarity))
    best_flat = np.unravel_index(best_index, similarity.shape)
    best_score = float(similarity[best_flat])
    if best_score < threshold:
        return None

    left_idx, right_idx = best_flat
    return _OverlapAnchor(
        left_node=left_methods[left_idx],
        right_node=right_methods[right_idx],
        overlap_kind=OverlapType.METHOD,
        match_type="semantic",
        overlap_score=best_score,
    )
