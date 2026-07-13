"""Regression tests for method-overlap golden set (data/patrol_method_overlap_golden.json)."""

from __future__ import annotations

import pytest
from backend.patrol.method_overlap import build_method_overlap_insight
from tests.fixtures.patrol_method_overlap_golden import (
    GoldenArchetype,
    MethodOverlapGoldenPair,
    build_graphs_for_pair,
    evaluate_method_overlap_golden_pair,
    golden_set_path,
    load_method_overlap_golden_set,
)
from tests.patrol.conftest import patch_patrol_settings
from tests.patrol.test_method_overlap_functional import _GoldenPcaEmbeddingClient, _NbLrNoiseEmbeddingClient


def test_method_overlap_golden_set_file_exists_and_validates() -> None:
    assert golden_set_path().is_file()
    golden = load_method_overlap_golden_set()
    assert golden.schema_version == 3
    assert golden.dataset_id == "patrol-method-overlap-golden"
    assert len(golden.pairs) == 3
    assert set(golden.baseline_matrix) == {
        "SYNONYM_TRUE_POSITIVE",
        "CORRELATED_FALSE_POSITIVE",
        "LITERAL_TRUE_POSITIVE",
    }


def test_method_overlap_golden_set_includes_nb_lr_false_positive_defect() -> None:
    golden = load_method_overlap_golden_set()
    defect = next(
        pair for pair in golden.pairs if pair.archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE
    )
    assert defect.issue_id == "NB_LR_FALSE_POSITIVE"
    assert defect.shared_topology.resonant_dataset_labels == []


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", load_method_overlap_golden_set().pairs, ids=lambda item: item.id)
async def test_method_overlap_golden_pair_mock_expectation(
    pair: MethodOverlapGoldenPair,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Functional gate with deterministic embedding clients per baseline archetype."""
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True, patrol_semantic_threshold=0.88)
    graphs = build_graphs_for_pair(pair)
    paper_ids = [pair.paper_a_id, pair.paper_b_id]

    if pair.archetype == GoldenArchetype.SYNONYM_TRUE_POSITIVE:
        embedding_client = _GoldenPcaEmbeddingClient()
    elif pair.archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE:
        embedding_client = _NbLrNoiseEmbeddingClient()
    else:
        embedding_client = None

    insight = await build_method_overlap_insight(
        graphs,
        paper_ids,
        embedding_client=embedding_client,
    )
    assert insight is not None
    passed, detail = evaluate_method_overlap_golden_pair(insight, pair)
    assert passed, detail
