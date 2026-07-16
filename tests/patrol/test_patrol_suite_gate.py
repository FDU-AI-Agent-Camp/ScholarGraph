"""Aggregated mock golden gate for all Patrol modes (V1 + V2) — P3 suite entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from backend.config import get_settings
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair
from backend.schemas.graph import GraphNode, NodeType
from scripts.benchmark_patrol_evaluators import (
    ClaimEvolutionEvaluator,
    ContradictionEvaluator,
    LensClashEvaluator,
    MethodOverlapEvaluator,
)
from tests.fixtures.patrol_golden_set import (
    GoldenPairEmbeddingClient,
    GoldenPairExpectation,
    GoldenPairRerankerClient,
    load_patrol_golden_set,
)
from tests.fixtures.patrol_method_overlap_golden import load_method_overlap_golden_set
from tests.fixtures.patrol_v1_golden_set import load_patrol_v1_golden_set
from tests.patrol.conftest import patch_patrol_settings


@dataclass(frozen=True, slots=True)
class SuiteCaseRef:
    mode: str
    case_id: str
    payload: Any


def collect_suite_cases() -> list[SuiteCaseRef]:
    refs: list[SuiteCaseRef] = []
    for case in load_patrol_v1_golden_set().cases:
        refs.append(SuiteCaseRef(mode=case.mode, case_id=case.id, payload=case))
    for pair in load_method_overlap_golden_set().pairs:
        refs.append(SuiteCaseRef(mode="method_overlap", case_id=pair.id, payload=pair))
    for pair in load_patrol_golden_set().pairs:
        refs.append(SuiteCaseRef(mode="claim_evolution", case_id=pair.id, payload=pair))
    return refs


_EVALUATOR_BY_MODE = {
    "lens_clash": LensClashEvaluator(),
    "contradiction": ContradictionEvaluator(),
    "method_overlap": MethodOverlapEvaluator(),
    "claim_evolution": ClaimEvolutionEvaluator(),
}


def test_patrol_suite_gate_inventory() -> None:
    cases = collect_suite_cases()
    assert len(cases) == 8 + 3 + 10
    modes = {case.mode for case in cases}
    assert modes == {"lens_clash", "contradiction", "method_overlap", "claim_evolution"}


@pytest.mark.asyncio
@pytest.mark.parametrize("suite_case", collect_suite_cases(), ids=lambda item: f"{item.mode}:{item.case_id}")
async def test_patrol_suite_gate_mock(suite_case: SuiteCaseRef, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unified mock gate — one parametrized entry for V1 + V2 golden sets."""
    if suite_case.mode == "claim_evolution":
        patch_patrol_settings(
            monkeypatch,
            reranker_enabled=True,
            patrol_claim_rq_coarse_threshold=0.42,
            patrol_claim_rq_rerank_threshold=0.60,
        )
    elif suite_case.mode == "method_overlap":
        patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True)

    settings = get_settings()
    evaluator = _EVALUATOR_BY_MODE[suite_case.mode]
    result = await evaluator.run_case(suite_case.payload, live=False, settings=settings)
    assert result.passed, f"{suite_case.mode}:{suite_case.case_id} failed — {result.detail}"


@pytest.mark.asyncio
async def test_suite_gate_claim_evolution_uses_mock_scores_not_live_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: suite gate must inject golden mock scores (not production clients)."""
    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    pair = next(pair for pair in load_patrol_golden_set().pairs if pair.id == "stem-neg-01")
    settings = get_settings()
    left = GraphNode(id="a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id="b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})
    aligned = await align_research_question_pair(
        [left],
        [right],
        embedding_client=GoldenPairEmbeddingClient(pair),
        settings=settings,
        reranker_client=GoldenPairRerankerClient(pair),
    )
    assert pair.expectation == GoldenPairExpectation.NEGATIVE
    assert aligned is None
