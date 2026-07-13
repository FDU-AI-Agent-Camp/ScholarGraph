#!/usr/bin/env python
"""Patrol 统一评估与全量 Benchmark 工具 (V2 Phase 3).

非 CI 强阻断；供架构评审与发布前大版本对标。关注整体指标量化演进。

多模式：
  --live     真实 Embedding / Reranker，产出线上评测报告
  --dry-run  硬编码 Stub 分数，验证漏斗链路（字面 → 语义 → 拓扑 → RAG → LLM）未被重构改坏

Usage (from repo root)::

    uv run python scripts/benchmark_patrol.py
    uv run python scripts/benchmark_patrol.py --mode method_overlap --dry-run
    uv run python scripts/benchmark_patrol.py --mode claim_evolution --live --concurrency 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import Settings, get_settings  # noqa: E402
from backend.llm.embeddings import get_embedding_client, reset_embedding_client_cache  # noqa: E402
from backend.llm.reranker import RerankerClient  # noqa: E402
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair  # noqa: E402
from backend.patrol.method_overlap import build_method_overlap_insight  # noqa: E402
from backend.schemas.graph import GraphNode, NodeType  # noqa: E402
from backend.schemas.patrol import MethodOverlapPoint, OverlapType, PatrolInsight, PatrolInsightStatus  # noqa: E402
from scripts.benchmark_patrol_metrics import (  # noqa: E402
    ClaimEvolutionCaseTelemetry,
    MethodOverlapCaseTelemetry,
    PathFamily,
    build_claim_evolution_metrics,
    build_method_overlap_metrics,
)
from tests.fixtures.patrol_golden_set import (  # noqa: E402
    GoldenPairEmbeddingClient,
    GoldenPairExpectation,
    GoldenPairRerankerClient,
    PatrolGoldenPair,
    load_patrol_golden_set,
)
from tests.fixtures.patrol_method_overlap_golden import (  # noqa: E402
    GoldenArchetype,
    GoldenExpectedStatus,
    MethodOverlapGoldenPair,
    build_graphs_for_pair,
    evaluate_method_overlap_golden_pair,
    load_method_overlap_golden_set,
)
from tests.patrol.method_overlap_live_engine import (  # noqa: E402
    assert_drift_guard,
    build_live_patrol_context,
    execute_method_overlap_funnel,
    measure_method_prescreen_cosine,
)
from tests.patrol.test_method_overlap_functional import (  # noqa: E402
    _GoldenPcaEmbeddingClient,
    _NbLrNoiseEmbeddingClient,
)

EXIT_SUCCESS = 0
EXIT_FAILED = 1
_EXIT_USAGE = 2
_REPORT_DIR = _REPO_ROOT / "data" / "benchmark_reports"
_DEFAULT_CONCURRENCY = 3
_CONCURRENCY_ENV = "PATROL_BENCHMARK_CONCURRENCY"
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


def _resolve_method_overlap_stub_client(archetype: GoldenArchetype) -> Any:
    if archetype == GoldenArchetype.SYNONYM_TRUE_POSITIVE:
        return _GoldenPcaEmbeddingClient()
    if archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE:
        return _NbLrNoiseEmbeddingClient()
    return None


def _method_overlap_points(insight: PatrolInsight) -> list[MethodOverlapPoint]:
    points: list[MethodOverlapPoint] = []
    for point in insight.structured_points:
        if isinstance(point, MethodOverlapPoint):
            points.append(point)
    return points


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


async def _eval_method_overlap_pair(
    pair: MethodOverlapGoldenPair,
    *,
    live: bool,
    settings: Settings,
) -> CaseResult:
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
            ctx = build_live_patrol_context(
                pair,
                embedding_client=embedding_client,
                settings=settings,
            )
            prescreen_cosine = await measure_method_prescreen_cosine(ctx)

    actual_status, actual_match_type, overlap_score, path_family, semantic_alarm = _extract_method_overlap_telemetry(
        insight,
        pair,
        prescreen_cosine=prescreen_cosine,
        settings=settings,
        drift_passed=drift_passed,
    )

    return CaseResult(
        case_id=pair.id,
        mode="method_overlap",
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


async def _eval_claim_evolution_pair(
    pair: PatrolGoldenPair,
    *,
    live: bool,
    settings: Settings,
) -> CaseResult:
    left = GraphNode(id=f"{pair.id}-a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id=f"{pair.id}-b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})

    coarse_score: float | None = None
    rerank_score: float | None = None

    if live and not settings.is_llm_mock and settings.patrol_claim_rq_funnel_enabled():
        aligned = await align_research_question_pair(
            [left],
            [right],
            embedding_client=get_embedding_client(),
            settings=settings,
            reranker_client=RerankerClient(settings),
        )
    else:
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
        mode="claim_evolution",
        archetype=None,
        expectation=pair.expectation.value,
        golden_polarity=golden_polarity,
        passed=passed,
        detail=detail,
        coarse_score=coarse_score,
        rerank_score=rerank_score,
    )


async def _run_with_semaphore(
    semaphore: asyncio.Semaphore,
    coro: Any,
) -> CaseResult:
    async with semaphore:
        return await coro


async def _run_method_overlap_cases(*, live: bool, concurrency: int) -> list[CaseResult]:
    golden = load_method_overlap_golden_set()
    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, min(concurrency, _MAX_CONCURRENCY)))
    tasks = [
        _run_with_semaphore(
            semaphore,
            _eval_method_overlap_pair(pair, live=live, settings=settings),
        )
        for pair in golden.pairs
    ]
    return list(await asyncio.gather(*tasks))


async def _run_claim_evolution_cases(*, live: bool, concurrency: int) -> list[CaseResult]:
    golden = load_patrol_golden_set()
    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, min(concurrency, _MAX_CONCURRENCY)))
    tasks = [
        _run_with_semaphore(
            semaphore,
            _eval_claim_evolution_pair(pair, live=live, settings=settings),
        )
        for pair in golden.pairs
    ]
    return list(await asyncio.gather(*tasks))


def _to_method_overlap_telemetry(results: list[CaseResult]) -> list[MethodOverlapCaseTelemetry]:
    rows: list[MethodOverlapCaseTelemetry] = []
    for row in results:
        if row.mode != "method_overlap":
            continue
        rows.append(
            MethodOverlapCaseTelemetry(
                case_id=row.case_id,
                archetype=row.archetype or "unknown",
                golden_polarity=row.golden_polarity,  # type: ignore[arg-type]
                expected_match_type=row.expected_match_type,
                passed=row.passed,
                actual_status=row.actual_status,
                actual_match_type=row.actual_match_type,
                overlap_score=row.overlap_score,
                theta_min=row.theta_min,
                prescreen_cosine=row.prescreen_cosine,
                semantic_threshold=row.semantic_threshold or 0.0,
                path_family=row.path_family or "none",
                semantic_prescreen_alarm=bool(row.semantic_prescreen_alarm),
                drift_passed=row.drift_passed,
            )
        )
    return rows


def _to_claim_evolution_telemetry(results: list[CaseResult]) -> list[ClaimEvolutionCaseTelemetry]:
    return [
        ClaimEvolutionCaseTelemetry(
            case_id=row.case_id,
            golden_polarity=row.golden_polarity,  # type: ignore[arg-type]
            passed=row.passed,
            coarse_score=row.coarse_score,
            rerank_score=row.rerank_score,
        )
        for row in results
        if row.mode == "claim_evolution"
    ]


def _build_report(
    mode: str,
    *,
    live: bool,
    concurrency: int,
    results: list[CaseResult],
) -> dict[str, Any]:
    passed_count = sum(1 for row in results if row.passed)
    method_rows = [row for row in results if row.mode == "method_overlap"]
    claim_rows = [row for row in results if row.mode == "claim_evolution"]

    evaluation_metrics: dict[str, Any] = {}
    if method_rows:
        evaluation_metrics["method_overlap"] = build_method_overlap_metrics(_to_method_overlap_telemetry(results))
    if claim_rows:
        evaluation_metrics["claim_evolution"] = build_claim_evolution_metrics(_to_claim_evolution_telemetry(results))

    funnel_note = (
        "production embedding/reranker — full API funnel"
        if live
        else "stub scores — validates literal→semantic→topology funnel wiring without API cost"
    )

    return {
        "benchmark_id": f"patrol-{mode}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "mode": mode,
        "live": live,
        "dry_run": not live,
        "concurrency": concurrency,
        "funnel_note": funnel_note,
        "totals": {
            "cases": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "pass_rate": round(passed_count / len(results), 4) if results else 0.0,
        },
        "evaluation_metrics": evaluation_metrics,
        "breakdown": [
            {
                "case_id": row.case_id,
                "mode": row.mode,
                "archetype": row.archetype,
                "expectation": row.expectation,
                "golden_polarity": row.golden_polarity,
                "passed": row.passed,
                "detail": row.detail,
                "actual_status": row.actual_status,
                "actual_match_type": row.actual_match_type,
                "overlap_score": row.overlap_score,
                "prescreen_cosine": row.prescreen_cosine,
                "path_family": row.path_family,
                "semantic_prescreen_alarm": row.semantic_prescreen_alarm,
                "drift_passed": row.drift_passed,
            }
            for row in results
        ],
    }


def _resolve_concurrency(cli_value: int) -> int:
    env_raw = os.environ.get(_CONCURRENCY_ENV, "").strip()
    if env_raw.isdigit():
        return max(1, min(int(env_raw), _MAX_CONCURRENCY))
    return max(1, min(cli_value, _MAX_CONCURRENCY))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patrol V2 统一评估 Benchmark")
    parser.add_argument(
        "--mode",
        choices=["method_overlap", "claim_evolution", "all"],
        default="all",
        help="金标子集（默认 all）",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="使用 live embedding / reranker（需 API 凭证）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stub 分数验证漏斗链路（默认行为，显式别名）",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_DEFAULT_CONCURRENCY,
        help=f"最大并发数 (Semaphore, default: {_DEFAULT_CONCURRENCY}, env: {_CONCURRENCY_ENV})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="报告输出路径（默认 data/benchmark_reports/patrol-{ts}.json）",
    )
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    live = args.live and not args.dry_run
    concurrency = _resolve_concurrency(args.concurrency)
    if live:
        from tests.fixtures.patrol_golden_config_snapshot import validate_golden_config_snapshot

        reset_embedding_client_cache()
        validate_golden_config_snapshot()

    modes = ["method_overlap", "claim_evolution"] if args.mode == "all" else [args.mode]
    all_results: list[CaseResult] = []
    for mode in modes:
        if mode == "method_overlap":
            all_results.extend(await _run_method_overlap_cases(live=live, concurrency=concurrency))
        else:
            all_results.extend(await _run_claim_evolution_cases(live=live, concurrency=concurrency))

    report = _build_report(args.mode, live=live, concurrency=concurrency, results=all_results)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or _REPORT_DIR / f"patrol-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[INFO] mode={args.mode} live={live} concurrency={concurrency}")
    print(f"[INFO] report={output_path}")
    print(json.dumps(report["totals"], ensure_ascii=False))
    if report.get("evaluation_metrics"):
        print(json.dumps(report["evaluation_metrics"], ensure_ascii=False, indent=2))

    return EXIT_SUCCESS if report["totals"]["failed"] == 0 else EXIT_FAILED


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
