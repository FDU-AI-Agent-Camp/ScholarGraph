"""Patrol benchmark evaluators — unified four-mode orchestration (P3)."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from backend.config import Settings, get_settings
from backend.llm.embeddings import get_embedding_client
from backend.llm.reranker import RerankerClient
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair
from backend.patrol.method_overlap import build_method_overlap_insight
from backend.schemas.graph import GraphNode, NodeType
from backend.schemas.patrol import MethodOverlapPoint, OverlapType, PatrolInsight, PatrolInsightStatus
from scripts.benchmark_patrol_metrics import PathFamily
from tests.fixtures.method_overlap_benchmark_stubs import GoldenPcaEmbeddingClient, NbLrNoiseEmbeddingClient
from tests.fixtures.patrol_golden_set import (
    GoldenPairEmbeddingClient,
    GoldenPairExpectation,
    GoldenPairRerankerClient,
    PatrolGoldenPair,
    load_patrol_golden_set,
)
from tests.fixtures.patrol_method_overlap_golden import (
    GoldenArchetype,
    GoldenExpectedStatus,
    MethodOverlapGoldenPair,
    build_graphs_for_pair,
    evaluate_method_overlap_golden_pair,
    load_method_overlap_golden_set,
)
from tests.fixtures.patrol_v1_golden_set import PatrolV1GoldenCase, evaluate_v1_golden_case, load_patrol_v1_golden_set
from tests.patrol.claim_evolution_live_engine import evaluate_claim_evolution_live_pair
from tests.patrol.method_overlap_live_engine import (
    assert_drift_guard,
    build_live_patrol_context,
    execute_method_overlap_funnel,
    measure_method_prescreen_cosine,
)

PATROL_MODES = ("lens_clash", "contradiction", "method_overlap", "claim_evolution")
_MAX_CONCURRENCY = 10


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    mode: str
    archetype: str | None
    expectation: str
    golden_polarity: str
    passed: bool
    detail: str
    actual_status: str | None = None
    actual_match_type: str | None = None
    overlap_score: float | None = None
    theta_min: float | None = None
    expected_match_type: str | None = None
    prescreen_cosine: float | None = None
    semantic_threshold: float | None = None
    path_family: PathFamily | None = None
    semantic_prescreen_alarm: bool | None = None
    drift_passed: bool | None = None
    coarse_score: float | None = None
    rerank_score: float | None = None
    live_coarse_score: float | None = None
    live_rerank_score: float | None = None
    drift_warnings: list[str] | None = None


def parse_mode_list(mode_arg: str) -> list[str]:
    if mode_arg == "all":
        return list(PATROL_MODES)
    modes = [item.strip() for item in mode_arg.split(",") if item.strip()]
    unknown = [mode for mode in modes if mode not in PATROL_MODES]
    if unknown:
        msg = f"unknown patrol mode(s): {', '.join(unknown)}; allowed={','.join(PATROL_MODES)}"
        raise ValueError(msg)
    return modes


def _resolve_method_overlap_stub_client(archetype: GoldenArchetype) -> Any:
    if archetype == GoldenArchetype.SYNONYM_TRUE_POSITIVE:
        return GoldenPcaEmbeddingClient()
    if archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE:
        return NbLrNoiseEmbeddingClient()
    return None


def _method_overlap_points(insight: PatrolInsight) -> list[MethodOverlapPoint]:
    return [point for point in insight.structured_points if isinstance(point, MethodOverlapPoint)]


def _extract_method_overlap_telemetry(
    insight: PatrolInsight,
    pair: MethodOverlapGoldenPair,
    *,
    prescreen_cosine: float | None,
    settings: Settings,
    drift_passed: bool | None,
) -> tuple[str | None, str | None, float | None, PathFamily, bool]:
    actual_status = insight.status.value
    threshold = settings.patrol_semantic_threshold
    semantic_alarm = prescreen_cosine is not None and prescreen_cosine >= threshold

    method_points = [point for point in _method_overlap_points(insight) if point.overlap_type == OverlapType.METHOD]
    if not method_points:
        method_points = _method_overlap_points(insight)

    actual_match_type: str | None = None
    overlap_score: float | None = None
    if method_points:
        primary = method_points[0]
        actual_match_type = primary.match_type
        overlap_score = primary.overlap_score

    if insight.status == PatrolInsightStatus.READY:
        path_family: PathFamily = "literal" if actual_match_type == "literal" else "semantic"
    elif semantic_alarm:
        path_family = "semantic_prescreen_alarm"
    elif insight.status == PatrolInsightStatus.INSUFFICIENT_DATA:
        path_family = "blocked_clean"
    else:
        path_family = "none"

    return actual_status, actual_match_type, overlap_score, path_family, semantic_alarm


def _golden_polarity_from_expectation(pair: MethodOverlapGoldenPair) -> str:
    if pair.expectation.expected_status == GoldenExpectedStatus.READY:
        return "positive"
    return "negative"


def _expectation_label(pair: MethodOverlapGoldenPair) -> str:
    match_type = pair.expectation.expected_match_type.value if pair.expectation.expected_match_type else "none"
    return f"{pair.expectation.expected_status.value}/{match_type}"


class BasePatrolEvaluator(ABC):
    mode: str

    @abstractmethod
    async def run_case(self, case: Any, *, live: bool, settings: Settings) -> CaseResult:
        """Evaluate one golden case."""

    async def run_cases(self, *, live: bool, concurrency: int) -> list[CaseResult]:
        settings = get_settings()
        cases = self.load_cases()
        semaphore = asyncio.Semaphore(max(1, min(concurrency, _MAX_CONCURRENCY)))
        tasks = [
            self._run_with_semaphore(semaphore, self.run_case(case, live=live, settings=settings)) for case in cases
        ]
        return list(await asyncio.gather(*tasks))

    @abstractmethod
    def load_cases(self) -> list[Any]:
        """Return golden cases for this evaluator."""

    async def _run_with_semaphore(self, semaphore: asyncio.Semaphore, coro: Any) -> CaseResult:
        async with semaphore:
            return await coro


class LensClashEvaluator(BasePatrolEvaluator):
    mode = "lens_clash"

    def load_cases(self) -> list[PatrolV1GoldenCase]:
        return [case for case in load_patrol_v1_golden_set().cases if case.mode == "lens_clash"]

    async def run_case(self, case: PatrolV1GoldenCase, *, live: bool, settings: Settings) -> CaseResult:
        passed, detail = await evaluate_v1_golden_case(case)
        return CaseResult(
            case_id=case.id,
            mode=self.mode,
            archetype=None,
            expectation=case.expectation.value,
            golden_polarity=case.expectation.value,
            passed=passed,
            detail=detail,
        )


class ContradictionEvaluator(BasePatrolEvaluator):
    mode = "contradiction"

    def load_cases(self) -> list[PatrolV1GoldenCase]:
        return [case for case in load_patrol_v1_golden_set().cases if case.mode == "contradiction"]

    async def run_case(self, case: PatrolV1GoldenCase, *, live: bool, settings: Settings) -> CaseResult:
        passed, detail = await evaluate_v1_golden_case(case)
        return CaseResult(
            case_id=case.id,
            mode=self.mode,
            archetype=None,
            expectation=case.expectation.value,
            golden_polarity=case.expectation.value,
            passed=passed,
            detail=detail,
        )


class MethodOverlapEvaluator(BasePatrolEvaluator):
    mode = "method_overlap"

    def load_cases(self) -> list[MethodOverlapGoldenPair]:
        return load_method_overlap_golden_set().pairs

    async def run_case(self, pair: MethodOverlapGoldenPair, *, live: bool, settings: Settings) -> CaseResult:
        graphs = build_graphs_for_pair(pair)
        paper_ids = [pair.paper_a_id, pair.paper_b_id]
        prescreen_cosine: float | None = None
        drift_passed: bool | None = None

        if live and not settings.is_llm_mock:
            ctx = build_live_patrol_context(pair, settings=settings)
            insight = await execute_method_overlap_funnel(ctx)
            passed, detail = evaluate_method_overlap_golden_pair(insight, pair)
            prescreen_cosine = await measure_method_prescreen_cosine(ctx)
            drift_passed, drift_detail = assert_drift_guard(prescreen_cosine, pair, settings=settings)
            if not drift_passed:
                passed = False
                detail = f"{detail}; drift_guard: {drift_detail}"
        else:
            embedding_client = _resolve_method_overlap_stub_client(pair.archetype)
            insight = await build_method_overlap_insight(
                graphs,
                paper_ids,
                embedding_client=embedding_client,
            )
            if insight is None:
                msg = f"build_method_overlap_insight returned None for {pair.id}"
                raise AssertionError(msg)
            passed, detail = evaluate_method_overlap_golden_pair(insight, pair)
            if embedding_client is not None:
                ctx = build_live_patrol_context(pair, embedding_client=embedding_client, settings=settings)
                prescreen_cosine = await measure_method_prescreen_cosine(ctx)

        actual_status, actual_match_type, overlap_score, path_family, semantic_alarm = (
            _extract_method_overlap_telemetry(
                insight,
                pair,
                prescreen_cosine=prescreen_cosine,
                settings=settings,
                drift_passed=drift_passed,
            )
        )

        return CaseResult(
            case_id=pair.id,
            mode=self.mode,
            archetype=pair.archetype.value,
            expectation=_expectation_label(pair),
            golden_polarity=_golden_polarity_from_expectation(pair),
            passed=passed,
            detail=detail,
            actual_status=actual_status,
            actual_match_type=actual_match_type,
            overlap_score=overlap_score,
            theta_min=pair.expectation.theta_min,
            expected_match_type=(
                pair.expectation.expected_match_type.value if pair.expectation.expected_match_type else None
            ),
            prescreen_cosine=prescreen_cosine,
            semantic_threshold=settings.patrol_semantic_threshold,
            path_family=path_family,
            semantic_prescreen_alarm=semantic_alarm,
            drift_passed=drift_passed,
        )


class ClaimEvolutionEvaluator(BasePatrolEvaluator):
    mode = "claim_evolution"

    def load_cases(self) -> list[PatrolGoldenPair]:
        return load_patrol_golden_set().pairs

    async def run_case(self, pair: PatrolGoldenPair, *, live: bool, settings: Settings) -> CaseResult:
        if live and not settings.is_llm_mock and settings.patrol_claim_rq_funnel_enabled():
            live_result = await evaluate_claim_evolution_live_pair(
                pair,
                embedding_client=get_embedding_client(),
                settings=settings,
                reranker_client=RerankerClient(settings),
            )
            for warning in live_result.performance_warnings:
                print(f"[Performance Warning] {pair.id}: {warning}")
            return CaseResult(
                case_id=pair.id,
                mode=self.mode,
                archetype=None,
                expectation=pair.expectation.value,
                golden_polarity="positive" if pair.expectation == GoldenPairExpectation.POSITIVE else "negative",
                passed=live_result.status_passed,
                detail=live_result.detail,
                live_coarse_score=live_result.live_coarse_score,
                live_rerank_score=live_result.live_rerank_score,
                coarse_score=pair.mock.coarse_similarity,
                rerank_score=pair.mock.rerank_score,
                drift_warnings=live_result.performance_warnings or None,
            )

        left = GraphNode(id=f"{pair.id}-a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
        right = GraphNode(id=f"{pair.id}-b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})
        coarse_score = pair.mock.coarse_similarity
        rerank_score = pair.mock.rerank_score
        aligned = await align_research_question_pair(
            [left],
            [right],
            embedding_client=GoldenPairEmbeddingClient(pair),
            settings=settings,
            reranker_client=GoldenPairRerankerClient(pair),
        )

        if pair.expectation == GoldenPairExpectation.POSITIVE:
            passed = aligned is not None
            detail = "aligned" if aligned else "blocked"
            golden_polarity = "positive"
        else:
            passed = aligned is None
            detail = "blocked" if aligned is None else "aligned"
            golden_polarity = "negative"

        return CaseResult(
            case_id=pair.id,
            mode=self.mode,
            archetype=None,
            expectation=pair.expectation.value,
            golden_polarity=golden_polarity,
            passed=passed,
            detail=detail,
            coarse_score=coarse_score,
            rerank_score=rerank_score,
        )


_EVALUATORS: dict[str, BasePatrolEvaluator] = {
    "lens_clash": LensClashEvaluator(),
    "contradiction": ContradictionEvaluator(),
    "method_overlap": MethodOverlapEvaluator(),
    "claim_evolution": ClaimEvolutionEvaluator(),
}


def get_evaluator(mode: str) -> BasePatrolEvaluator:
    return _EVALUATORS[mode]


async def run_benchmark_modes(modes: list[str], *, live: bool, concurrency: int) -> list[CaseResult]:
    results: list[CaseResult] = []
    for mode in modes:
        results.extend(await get_evaluator(mode).run_cases(live=live, concurrency=concurrency))
    return results
