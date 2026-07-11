"""Regression tests for patrol claim-evolution RQ golden set (data/patrol_golden_set.json)."""

from __future__ import annotations

import pytest
from backend.config import get_settings
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair
from backend.schemas.graph import GraphNode, NodeType
from tests.fixtures.patrol_golden_set import (
    GoldenPairEmbeddingClient,
    GoldenPairExpectation,
    GoldenPairRerankerClient,
    PatrolGoldenPair,
    golden_set_path,
    load_patrol_golden_set,
)
from tests.patrol.conftest import patch_patrol_settings


def test_patrol_golden_set_file_exists_and_validates() -> None:
    assert golden_set_path().is_file()
    golden = load_patrol_golden_set()
    assert golden.dataset_id == "patrol-claim-evolution-rq-golden"
    assert len(golden.pairs) == 10

    paradigms = {pair.paradigm for pair in golden.pairs}
    assert paradigms == {"STEM", "HSS"}
    assert sum(1 for pair in golden.pairs if pair.paradigm == "STEM") == 5
    assert sum(1 for pair in golden.pairs if pair.paradigm == "HSS") == 5

    expectations = {pair.expectation for pair in golden.pairs}
    assert expectations == {GoldenPairExpectation.POSITIVE, GoldenPairExpectation.NEGATIVE}
    assert sum(1 for pair in golden.pairs if pair.expectation == GoldenPairExpectation.POSITIVE) == 5
    assert sum(1 for pair in golden.pairs if pair.expectation == GoldenPairExpectation.NEGATIVE) == 5


def test_patrol_golden_set_includes_canonical_macro_micro_negative() -> None:
    golden = load_patrol_golden_set()
    canonical = next(pair for pair in golden.pairs if pair.id == "hss-neg-01")
    assert canonical.expectation == GoldenPairExpectation.NEGATIVE
    assert canonical.label_a == "The impact of social media on political participation."
    assert canonical.label_b == "Does Weibo usage increase voter turnout in local elections?"


def test_patrol_golden_set_includes_canonical_stem_positive() -> None:
    golden = load_patrol_golden_set()
    canonical = next(pair for pair in golden.pairs if pair.id == "stem-pos-01")
    assert canonical.expectation == GoldenPairExpectation.POSITIVE
    assert "deep learning" in canonical.label_a.lower()
    assert "convolutional neural networks" in canonical.label_b.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", load_patrol_golden_set().pairs, ids=lambda item: item.id)
async def test_patrol_golden_pair_rq_gate_expectation(
    pair: PatrolGoldenPair,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each golden pair must pass or fail the two-stage RQ gate per its label."""
    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    settings = get_settings()

    left = GraphNode(id=f"{pair.id}-a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id=f"{pair.id}-b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})

    aligned = await align_research_question_pair(
        [left],
        [right],
        embedding_client=GoldenPairEmbeddingClient(pair),
        settings=settings,
        reranker_client=GoldenPairRerankerClient(pair),
    )

    if pair.expectation == GoldenPairExpectation.POSITIVE:
        assert aligned is not None
        assert aligned[0].label == pair.label_a
        assert aligned[1].label == pair.label_b
    else:
        assert aligned is None
