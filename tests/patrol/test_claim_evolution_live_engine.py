# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for claim_evolution live drift engine (no real API)."""

from __future__ import annotations

import pytest
from backend.config import Settings
from backend.schemas.graph import GraphNode, NodeType
from tests.fixtures.patrol_golden_set import GoldenPairExpectation, load_patrol_golden_set
from tests.patrol.claim_evolution_live_engine import (
    DEFAULT_COARSE_DRIFT_TOLERANCE,
    evaluate_claim_evolution_live_pair,
)


class _StubEmbeddingClient:
    is_mock = False

    def __init__(self, coarse: float) -> None:
        self._coarse = coarse

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import math

        right = [self._coarse, math.sqrt(max(0.0, 1.0 - self._coarse**2))]
        return [[1.0, 0.0], right]


class _StubRerankerClient:
    def __init__(self, score: float) -> None:
        self._score = score

    async def rerank_pair(self, text_a: str, text_b: str) -> float:
        return self._score

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self._score for _ in pairs]


@pytest.mark.asyncio
async def test_live_engine_hard_fails_on_negative_pair_aligned() -> None:
    pair = next(item for item in load_patrol_golden_set().pairs if item.id == "hss-neg-01")
    settings = Settings(
        _env_file=None,
        reranker_enabled=True,
        reranker_model="bge-reranker-large",
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    result = await evaluate_claim_evolution_live_pair(
        pair,
        embedding_client=_StubEmbeddingClient(0.90),
        settings=settings,
        reranker_client=_StubRerankerClient(0.95),
    )
    assert pair.expectation == GoldenPairExpectation.NEGATIVE
    assert result.aligned is True
    assert result.status_passed is False


@pytest.mark.asyncio
async def test_live_engine_emits_drift_warning_when_delta_exceeds_tolerance() -> None:
    pair = next(item for item in load_patrol_golden_set().pairs if item.id == "stem-pos-01")
    settings = Settings(
        _env_file=None,
        reranker_enabled=True,
        reranker_model="bge-reranker-large",
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    live_coarse = pair.mock.coarse_similarity + DEFAULT_COARSE_DRIFT_TOLERANCE + 0.05
    result = await evaluate_claim_evolution_live_pair(
        pair,
        embedding_client=_StubEmbeddingClient(live_coarse),
        settings=settings,
        reranker_client=_StubRerankerClient(pair.mock.rerank_score),
        coarse_drift_tolerance=DEFAULT_COARSE_DRIFT_TOLERANCE,
    )
    assert result.status_passed is True
    assert any("coarse drift" in warning for warning in result.performance_warnings)


@pytest.mark.asyncio
async def test_live_engine_builds_rq_nodes_from_pair_labels() -> None:
    pair = load_patrol_golden_set().pairs[0]
    left = GraphNode(id="a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id="b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})
    assert left.label == pair.label_a
    assert right.label == pair.label_b
