# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Two-stage ResearchQuestion alignment gate for claim_evolution (TD-4).

Stage 1 — Bi-encoder coarse recall at a relaxed cosine threshold.
Stage 2 — Cross-encoder rerank fine gate when ``reranker_enabled`` is true.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.llm.reranker import RerankerClient
from backend.patrol.node_selection import select_primary_node
from backend.patrol.similarity import cosine_similarity
from backend.schemas.graph import GraphNode

if TYPE_CHECKING:
    from backend.config import Settings
    from backend.llm.embeddings import EmbeddingClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _QuestionPairCandidate:
    left: GraphNode
    right: GraphNode
    coarse_score: float


def _dedupe_nodes(nodes: list[GraphNode]) -> list[GraphNode]:
    seen: set[str] = set()
    unique: list[GraphNode] = []
    for node in nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        unique.append(node)
    return unique


async def _pair_coarse_similarity(
    left: GraphNode,
    right: GraphNode,
    embedding_client: EmbeddingClient,
) -> float:
    vectors = await embedding_client.embed_texts([left.label, right.label])
    if len(vectors) != 2:
        return 0.0
    return cosine_similarity(vectors[0], vectors[1])


async def _coarse_filter_candidates(
    left_nodes: list[GraphNode],
    right_nodes: list[GraphNode],
    embedding_client: EmbeddingClient,
    coarse_threshold: float,
) -> list[_QuestionPairCandidate]:
    candidates: list[_QuestionPairCandidate] = []
    for left in left_nodes:
        for right in right_nodes:
            coarse_score = await _pair_coarse_similarity(left, right, embedding_client)
            if coarse_score >= coarse_threshold:
                candidates.append(_QuestionPairCandidate(left, right, coarse_score))
    candidates.sort(key=lambda item: item.coarse_score, reverse=True)
    return candidates


async def _select_with_reranker(
    candidates: list[_QuestionPairCandidate],
    *,
    settings: Settings,
    reranker_client: RerankerClient | None,
    rerank_threshold: float,
    max_candidates: int,
) -> tuple[GraphNode, GraphNode] | None:
    client = reranker_client or RerankerClient(settings)
    shortlist = candidates[:max_candidates]
    pair_texts = [(item.left.label, item.right.label) for item in shortlist]
    rerank_scores = await client.rerank_pairs(pair_texts)

    best_index = -1
    best_score = -1.0
    for index, score in enumerate(rerank_scores):
        if score >= rerank_threshold and score > best_score:
            best_score = score
            best_index = index

    if best_index < 0:
        logger.info(
            "claim_evolution_rerank_rejected",
            extra={
                "candidate_count": len(shortlist),
                "rerank_threshold": rerank_threshold,
                "top_rerank_score": max(rerank_scores) if rerank_scores else None,
            },
        )
        return None

    winner = shortlist[best_index]
    logger.info(
        "claim_evolution_rerank_passed",
        extra={
            "left_node_id": winner.left.id,
            "right_node_id": winner.right.id,
            "coarse_score": winner.coarse_score,
            "rerank_score": best_score,
        },
    )
    return winner.left, winner.right


def _select_with_strict_embedding_fallback(
    candidates: list[_QuestionPairCandidate],
    *,
    settings: Settings,
) -> tuple[GraphNode, GraphNode] | None:
    """Reranker-off fallback: best coarse pair must still clear the legacy strict gate."""
    best = candidates[0]
    strict_threshold = settings.patrol_claim_rq_threshold_effective(
        best.left.label,
        best.right.label,
    )
    if best.coarse_score >= strict_threshold:
        return best.left, best.right
    return None


async def align_research_question_pair(
    left_nodes: list[GraphNode],
    right_nodes: list[GraphNode],
    *,
    embedding_client: EmbeddingClient,
    settings: Settings,
    reranker_client: RerankerClient | None = None,
) -> tuple[GraphNode, GraphNode] | None:
    """Return the best aligned question/thesis pair or ``None`` when the funnel rejects all."""
    left_pool = _dedupe_nodes(left_nodes)
    right_pool = _dedupe_nodes(right_nodes)
    if not left_pool or not right_pool:
        return None

    if getattr(embedding_client, "is_mock", False):
        left = select_primary_node(left_pool)
        right = select_primary_node(right_pool)
        if left is None or right is None:
            return None
        if left.label.strip().lower() == right.label.strip().lower():
            return left, right
        return None

    try:
        candidates = await _coarse_filter_candidates(
            left_pool,
            right_pool,
            embedding_client,
            settings.patrol_claim_rq_coarse_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "patrol_claim_rq_gate_degraded",
            extra={"reason": "embedding_failed", "error": str(exc)},
        )
        return None

    if not candidates:
        logger.info(
            "claim_evolution_coarse_rejected", extra={"left_count": len(left_pool), "right_count": len(right_pool)}
        )
        return None

    if settings.reranker_enabled:
        try:
            return await _select_with_reranker(
                candidates,
                settings=settings,
                reranker_client=reranker_client,
                rerank_threshold=settings.patrol_claim_rq_rerank_threshold,
                max_candidates=settings.patrol_claim_rq_max_rerank_candidates,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "patrol_claim_rq_gate_degraded",
                extra={"reason": "reranker_failed", "error": str(exc)},
            )
            return _select_with_strict_embedding_fallback(candidates, settings=settings)

    return _select_with_strict_embedding_fallback(candidates, settings=settings)
