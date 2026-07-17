# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for claim_evolution two-stage RQ alignment gate."""

import math

import pytest
from backend.config import Settings
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair
from backend.schemas.graph import GraphNode, NodeType


class _GateEmbeddingClient:
    is_mock = False

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors.get(text, [0.0, 0.0]).copy() for text in texts]


class _GateRerankerClient:
    def __init__(self, scores: dict[tuple[str, str], float]) -> None:
        self._scores = scores

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self._scores.get(pair, 0.0) for pair in pairs]


@pytest.mark.asyncio
async def test_rq_gate_coarse_filters_before_rerank() -> None:
    left = GraphNode(id="l1", label="Q macro social media", type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id="r1", label="Q micro weibo voting", type=NodeType.RESEARCH_QUESTION, data={})
    unrelated = GraphNode(id="r2", label="Q unrelated topic", type=NodeType.RESEARCH_QUESTION, data={})

    cosine = 0.75
    micro_vector = [cosine, math.sqrt(1.0 - cosine**2)]
    embedding = _GateEmbeddingClient(
        {
            "Q macro social media": [1.0, 0.0],
            "Q micro weibo voting": micro_vector,
            "Q unrelated topic": [0.0, 1.0],
        }
    )
    settings = Settings(
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    reranker = _GateRerankerClient(
        {
            ("Q macro social media", "Q micro weibo voting"): 0.45,
            ("Q macro social media", "Q unrelated topic"): 0.90,
        }
    )

    aligned = await align_research_question_pair(
        [left],
        [right, unrelated],
        embedding_client=embedding,
        settings=settings,
        reranker_client=reranker,
    )

    assert aligned is None


@pytest.mark.asyncio
async def test_rq_gate_rerank_selects_best_passing_pair() -> None:
    left = GraphNode(id="l1", label="Q-A", type=NodeType.RESEARCH_QUESTION, data={})
    right_a = GraphNode(id="r1", label="Q-B", type=NodeType.RESEARCH_QUESTION, data={})
    right_b = GraphNode(id="r2", label="Q-C", type=NodeType.RESEARCH_QUESTION, data={})

    embedding = _GateEmbeddingClient(
        {
            "Q-A": [1.0, 0.0],
            "Q-B": [0.95, 0.31],
            "Q-C": [0.94, 0.34],
        }
    )
    settings = Settings(
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    reranker = _GateRerankerClient(
        {
            ("Q-A", "Q-B"): 0.55,
            ("Q-A", "Q-C"): 0.88,
        }
    )

    aligned = await align_research_question_pair(
        [left],
        [right_a, right_b],
        embedding_client=embedding,
        settings=settings,
        reranker_client=reranker,
    )

    assert aligned is not None
    assert aligned[0].id == "l1"
    assert aligned[1].id == "r2"


class _FailingEmbeddingClient:
    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding endpoint unavailable")


class _FailingRerankerClient:
    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        raise RuntimeError("reranker endpoint unavailable")


@pytest.mark.asyncio
async def test_rq_gate_degrades_when_embedding_fails() -> None:
    left = GraphNode(id="l1", label="Q-A", type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id="r1", label="Q-B", type=NodeType.RESEARCH_QUESTION, data={})
    settings = Settings(
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )

    aligned = await align_research_question_pair(
        [left],
        [right],
        embedding_client=_FailingEmbeddingClient(),
        settings=settings,
    )

    assert aligned is None


@pytest.mark.asyncio
async def test_rq_gate_reranker_failure_falls_back_to_strict_embedding() -> None:
    left = GraphNode(id="l1", label="Q-A", type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id="r1", label="Q-B", type=NodeType.RESEARCH_QUESTION, data={})
    embedding = _GateEmbeddingClient(
        {
            "Q-A": [1.0, 0.0],
            "Q-B": [0.95, 0.31],
        }
    )
    settings = Settings(
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
        patrol_claim_rq_threshold=0.75,
    )

    aligned = await align_research_question_pair(
        [left],
        [right],
        embedding_client=embedding,
        settings=settings,
        reranker_client=_FailingRerankerClient(),
    )

    assert aligned is not None
    assert aligned[0].label == "Q-A"
    assert aligned[1].label == "Q-B"
