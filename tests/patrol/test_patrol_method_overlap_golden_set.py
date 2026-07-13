"""Regression tests for method-overlap golden set (data/patrol_method_overlap_golden.json)."""

from __future__ import annotations

import pytest
from backend.patrol.method_overlap import build_method_overlap_insight
from backend.schemas.patrol import PatrolInsightStatus
from tests.fixtures.patrol_method_overlap_golden import (
    MethodOverlapGoldenExpectation,
    MethodOverlapGoldenPair,
    build_graphs_for_pair,
    golden_set_path,
    load_method_overlap_golden_set,
)
from tests.patrol.conftest import patch_patrol_settings
from tests.patrol.test_method_overlap_functional import _GoldenPcaEmbeddingClient, _NbLrNoiseEmbeddingClient


class _DistinctLabelEmbeddingClient:
    """Deterministic distinct vectors per label for negative-pair mock runs."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for index, text in enumerate(texts):
            base = float((hash(text) % 97) + 1) / 100.0
            vectors.append([base, 1.0 - base, float(index % 3) * 0.01])
        return vectors


def test_method_overlap_golden_set_file_exists_and_validates() -> None:
    assert golden_set_path().is_file()
    golden = load_method_overlap_golden_set()
    assert golden.dataset_id == "patrol-method-overlap-golden"
    assert len(golden.pairs) == 4
    assert all(pair.paradigm == "STEM" for pair in golden.pairs)


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", load_method_overlap_golden_set().pairs, ids=lambda item: item.id)
async def test_method_overlap_golden_pair_mock_expectation(
    pair: MethodOverlapGoldenPair,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Functional gate with deterministic embedding clients per pair archetype."""
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True, patrol_semantic_threshold=0.88)
    graphs = build_graphs_for_pair(pair)
    paper_ids = [pair.paper_a_id, pair.paper_b_id]

    if pair.id == "stem-pos-01":
        embedding_client = _GoldenPcaEmbeddingClient()
    elif pair.id == "stem-neg-01":
        embedding_client = _NbLrNoiseEmbeddingClient()
    else:
        embedding_client = _DistinctLabelEmbeddingClient()

    insight = await build_method_overlap_insight(
        graphs,
        paper_ids,
        embedding_client=embedding_client,
    )
    assert insight is not None

    if pair.expectation == MethodOverlapGoldenExpectation.POSITIVE:
        assert insight.status == PatrolInsightStatus.READY
        assert len(insight.structured_points) >= 1
    else:
        assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
        assert insight.structured_points == []
