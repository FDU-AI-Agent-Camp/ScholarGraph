"""Live claim_evolution RQ gate measurement with drift tolerance (P4)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings
from backend.llm.embeddings import EmbeddingClient
from backend.llm.reranker import RerankerClient
from backend.patrol.claim_evolution_rq_gate import (
    _coarse_filter_candidates,
    _pair_coarse_similarity,
    align_research_question_pair,
)
from backend.schemas.graph import GraphNode, NodeType
from tests.fixtures.patrol_golden_set import GoldenPairExpectation, PatrolGoldenPair

DEFAULT_COARSE_DRIFT_TOLERANCE = 0.15
DEFAULT_RERANK_DRIFT_TOLERANCE = 0.20
THRESHOLD_MARGIN_WARNING_BAND = 0.05


@dataclass(frozen=True, slots=True)
class ClaimEvolutionLiveResult:
    pair_id: str
    status_passed: bool
    aligned: bool
    detail: str
    live_coarse_score: float | None
    live_rerank_score: float | None
    mock_coarse_score: float
    mock_rerank_score: float
    coarse_delta: float | None
    rerank_delta: float | None
    performance_warnings: list[str]


def _score_margin_warnings(
    *,
    coarse_score: float | None,
    rerank_score: float | None,
    coarse_threshold: float,
    rerank_threshold: float,
) -> list[str]:
    warnings: list[str] = []
    if coarse_score is not None and abs(coarse_score - coarse_threshold) <= THRESHOLD_MARGIN_WARNING_BAND:
        warnings.append(
            f"coarse score {coarse_score:.4f} is within {THRESHOLD_MARGIN_WARNING_BAND} of "
            f"PATROL_CLAIM_RQ_COARSE_THRESHOLD={coarse_threshold}"
        )
    if rerank_score is not None and abs(rerank_score - rerank_threshold) <= THRESHOLD_MARGIN_WARNING_BAND:
        warnings.append(
            f"rerank score {rerank_score:.4f} is within {THRESHOLD_MARGIN_WARNING_BAND} of "
            f"PATROL_RERANK_THRESHOLD={rerank_threshold}"
        )
    return warnings


def _drift_warnings(
    *,
    coarse_delta: float | None,
    rerank_delta: float | None,
    coarse_tolerance: float,
    rerank_tolerance: float,
) -> list[str]:
    warnings: list[str] = []
    if coarse_delta is not None and coarse_delta > coarse_tolerance:
        warnings.append(f"coarse drift Δ={coarse_delta:.4f} exceeds tolerance {coarse_tolerance}")
    if rerank_delta is not None and rerank_delta > rerank_tolerance:
        warnings.append(f"rerank drift Δ={rerank_delta:.4f} exceeds tolerance {rerank_tolerance}")
    return warnings


async def measure_live_rq_gate_scores(
    left: GraphNode,
    right: GraphNode,
    *,
    embedding_client: EmbeddingClient,
    settings: Settings,
    reranker_client: RerankerClient,
) -> tuple[float | None, float | None]:
    """Return best coarse cosine and rerank score for the pair."""
    coarse_score = await _pair_coarse_similarity(left, right, embedding_client)
    rerank_score: float | None = None
    if settings.reranker_enabled:
        candidates = await _coarse_filter_candidates(
            [left],
            [right],
            embedding_client,
            settings.patrol_claim_rq_coarse_threshold,
        )
        if candidates:
            pair_texts = [(candidates[0].left.label, candidates[0].right.label)]
            scores = await reranker_client.rerank_pairs(pair_texts)
            if scores:
                rerank_score = scores[0]
    return coarse_score, rerank_score


async def evaluate_claim_evolution_live_pair(
    pair: PatrolGoldenPair,
    *,
    embedding_client: EmbeddingClient,
    settings: Settings,
    reranker_client: RerankerClient,
    coarse_drift_tolerance: float = DEFAULT_COARSE_DRIFT_TOLERANCE,
    rerank_drift_tolerance: float = DEFAULT_RERANK_DRIFT_TOLERANCE,
) -> ClaimEvolutionLiveResult:
    """Hard-fail on label mismatch; soft-warn on score drift near thresholds."""
    left = GraphNode(id=f"{pair.id}-a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id=f"{pair.id}-b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})

    aligned = await align_research_question_pair(
        [left],
        [right],
        embedding_client=embedding_client,
        settings=settings,
        reranker_client=reranker_client,
    )
    live_coarse, live_rerank = await measure_live_rq_gate_scores(
        left,
        right,
        embedding_client=embedding_client,
        settings=settings,
        reranker_client=reranker_client,
    )

    aligned_bool = aligned is not None
    if pair.expectation == GoldenPairExpectation.POSITIVE:
        status_passed = aligned_bool
        detail = "aligned" if aligned_bool else "blocked"
    else:
        status_passed = not aligned_bool
        detail = "blocked" if not aligned_bool else "aligned"

    coarse_delta = abs(live_coarse - pair.mock.coarse_similarity) if live_coarse is not None else None
    rerank_delta = abs(live_rerank - pair.mock.rerank_score) if live_rerank is not None else None

    warnings = _score_margin_warnings(
        coarse_score=live_coarse,
        rerank_score=live_rerank,
        coarse_threshold=settings.patrol_claim_rq_coarse_threshold,
        rerank_threshold=settings.patrol_claim_rq_rerank_threshold,
    )
    if status_passed:
        warnings.extend(
            _drift_warnings(
                coarse_delta=coarse_delta,
                rerank_delta=rerank_delta,
                coarse_tolerance=coarse_drift_tolerance,
                rerank_tolerance=rerank_drift_tolerance,
            )
        )

    return ClaimEvolutionLiveResult(
        pair_id=pair.id,
        status_passed=status_passed,
        aligned=aligned_bool,
        detail=detail,
        live_coarse_score=live_coarse,
        live_rerank_score=live_rerank,
        mock_coarse_score=pair.mock.coarse_similarity,
        mock_rerank_score=pair.mock.rerank_score,
        coarse_delta=coarse_delta,
        rerank_delta=rerank_delta,
        performance_warnings=warnings,
    )
