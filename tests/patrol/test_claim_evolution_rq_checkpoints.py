# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""合入红线：claim_evolution 双阶段 RQ 漏斗宏微观拦截与跨语言放行卡点。"""

from __future__ import annotations

import math

import pytest
from backend.config import get_settings
from backend.patrol.claim_evolution import build_claim_evolution_insight
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair
from backend.patrol.similarity import cosine_similarity
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol import ClaimEvolutionPoint, PatrolInsightStatus
from tests.fixtures.patrol_golden_set import load_patrol_golden_set
from tests.helpers.patrol_graphs import build_stem_graph_with_question_claim
from tests.patrol.conftest import patch_patrol_settings

_CHECKPOINT_COARSE_THRESHOLD = 0.42
_CHECKPOINT_RERANK_THRESHOLD = 0.60
_MACRO_MICRO_COARSE_SCORE = 0.78
_MACRO_MICRO_RERANK_SCORE = 0.35

_CROSS_LINGUAL_ZH = "深度学习如何提升图像识别准确率？"
_CROSS_LINGUAL_EN = "How does deep learning improve image recognition accuracy?"
_CROSS_LINGUAL_COARSE_SCORE = 0.76
_CROSS_LINGUAL_RERANK_SCORE = 0.84


def _vector_pair_for_cosine(similarity: float) -> tuple[list[float], list[float]]:
    clamped = max(-1.0, min(1.0, similarity))
    return [1.0, 0.0], [clamped, math.sqrt(max(0.0, 1.0 - clamped**2))]


class _CheckpointEmbeddingClient:
    is_mock = False

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors.get(text, [0.0, 0.0]).copy() for text in texts]


class _FixedScoreRerankerClient:
    def __init__(self, score: float) -> None:
        self._score = score

    async def rerank_pair(self, text_a: str, text_b: str) -> float:
        return self._score

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self._score for _ in pairs]


@pytest.fixture
def checkpoint_rq_gate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=_CHECKPOINT_COARSE_THRESHOLD,
        patrol_claim_rq_rerank_threshold=_CHECKPOINT_RERANK_THRESHOLD,
    )


@pytest.mark.asyncio
async def test_claim_evolution_checkpoint_negative_macro_micro_social_media_weibo(
    checkpoint_rq_gate_settings: None,
) -> None:
    """宏微观拦截断言：粗筛 0.78 通过，精排 0.35 拦截 → INSUFFICIENT_DATA。"""
    golden = next(pair for pair in load_patrol_golden_set().pairs if pair.id == "hss-neg-01")
    macro_label = golden.label_a
    micro_label = golden.label_b

    left_vector, right_vector = _vector_pair_for_cosine(_MACRO_MICRO_COARSE_SCORE)
    embedding_client = _CheckpointEmbeddingClient(
        {
            macro_label: left_vector,
            micro_label: right_vector,
        }
    )
    measured_coarse = cosine_similarity(left_vector, right_vector)
    assert measured_coarse == pytest.approx(_MACRO_MICRO_COARSE_SCORE, abs=1e-6)
    assert measured_coarse >= _CHECKPOINT_COARSE_THRESHOLD

    left_node = GraphNode(id="rq_macro", label=macro_label, type=NodeType.RESEARCH_QUESTION, data={})
    right_node = GraphNode(id="rq_micro", label=micro_label, type=NodeType.RESEARCH_QUESTION, data={})
    reranker = _FixedScoreRerankerClient(_MACRO_MICRO_RERANK_SCORE)
    settings = get_settings()

    aligned = await align_research_question_pair(
        [left_node],
        [right_node],
        embedding_client=embedding_client,
        settings=settings,
        reranker_client=reranker,
    )
    assert aligned is None
    assert _MACRO_MICRO_RERANK_SCORE < _CHECKPOINT_RERANK_THRESHOLD

    graphs = {
        "hss-macro": UnifiedPaperGraph(
            paper_id="hss-macro",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n_thesis", label=macro_label, type=NodeType.THESIS, data={}),
                GraphNode(
                    id="n_claim",
                    label="Social media broadly shapes civic engagement.",
                    type=NodeType.CLAIM,
                    data={},
                ),
            ],
            edges=[],
        ),
        "hss-micro": UnifiedPaperGraph(
            paper_id="hss-micro",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n_thesis", label=micro_label, type=NodeType.THESIS, data={}),
                GraphNode(
                    id="n_claim",
                    label="Weibo usage slightly raises local turnout.",
                    type=NodeType.CLAIM,
                    data={},
                ),
            ],
            edges=[],
        ),
    }
    insight = await build_claim_evolution_insight(
        graphs,
        ["hss-macro", "hss-micro"],
        embedding_client=embedding_client,
        reranker_client=reranker,
    )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


@pytest.mark.asyncio
async def test_claim_evolution_checkpoint_positive_cross_lingual_paraphrase_ready(
    checkpoint_rq_gate_settings: None,
) -> None:
    """跨语言同义转述放行断言：字面不同、语义等价，粗筛+精排通过 → READY。"""
    left_vector, right_vector = _vector_pair_for_cosine(_CROSS_LINGUAL_COARSE_SCORE)
    embedding_client = _CheckpointEmbeddingClient(
        {
            _CROSS_LINGUAL_ZH: left_vector,
            _CROSS_LINGUAL_EN: right_vector,
        }
    )
    measured_coarse = cosine_similarity(left_vector, right_vector)
    assert measured_coarse == pytest.approx(_CROSS_LINGUAL_COARSE_SCORE, abs=1e-6)
    assert measured_coarse >= _CHECKPOINT_COARSE_THRESHOLD

    reranker = _FixedScoreRerankerClient(_CROSS_LINGUAL_RERANK_SCORE)
    assert _CROSS_LINGUAL_RERANK_SCORE >= _CHECKPOINT_RERANK_THRESHOLD

    graphs = {
        "stem-zh": build_stem_graph_with_question_claim(
            "stem-zh",
            question_label=_CROSS_LINGUAL_ZH,
            claim_label="实验显示深度学习可将 Top-1 准确率提升 4.2 个百分点。",
        ),
        "stem-en": build_stem_graph_with_question_claim(
            "stem-en",
            question_label=_CROSS_LINGUAL_EN,
            claim_label="Experiments show deep learning improves Top-1 accuracy by 4.2 points.",
        ),
    }
    insight = await build_claim_evolution_insight(
        graphs,
        ["stem-zh", "stem-en"],
        embedding_client=embedding_client,
        reranker_client=reranker,
    )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert point.research_question in {_CROSS_LINGUAL_ZH, _CROSS_LINGUAL_EN}
    assert point.paper_a_claim
    assert point.paper_b_claim
