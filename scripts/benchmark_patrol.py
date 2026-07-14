#!/usr/bin/env python
"""Patrol 统一评估与四模式 Benchmark 编排 (P3).

覆盖 V1 (lens_clash / contradiction) 与 V2 (method_overlap / claim_evolution) 金标。

Usage (from repo root)::

    uv run python scripts/benchmark_patrol.py
    uv run python scripts/benchmark_patrol.py --mode method_overlap --dry-run
    uv run python scripts/benchmark_patrol.py --mode all --live --concurrency 2
    uv run python scripts/benchmark_patrol.py --mode lens_clash,claim_evolution
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("APP_PROFILE", "ci")
os.environ.setdefault("SCHOLARGRAPH_IGNORE_DOTENV", "1")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("RERANKER_ENABLED", "true")
os.environ.setdefault("RERANKER_MODEL", "bge-reranker-large")

from backend.config import get_settings  # noqa: E402
from backend.llm.embeddings import reset_embedding_client_cache  # noqa: E402
from scripts.benchmark_patrol_evaluators import (  # noqa: E402
    PATROL_MODES,
    CaseResult,
    parse_mode_list,
    run_benchmark_modes,
)
from scripts.benchmark_patrol_metrics import (  # noqa: E402
    ClaimEvolutionCaseTelemetry,
    MethodOverlapCaseTelemetry,
    V1CaseTelemetry,
    build_claim_evolution_metrics,
    build_method_overlap_metrics,
    build_v1_mode_metrics,
)

EXIT_SUCCESS = 0
EXIT_FAILED = 1
_EXIT_USAGE = 2
_REPORT_DIR = _REPO_ROOT / "data" / "benchmark_reports"
_DEFAULT_CONCURRENCY = 3
_CONCURRENCY_ENV = "PATROL_BENCHMARK_CONCURRENCY"
_MAX_CONCURRENCY = 10


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
            live_coarse_score=row.live_coarse_score,
            live_rerank_score=row.live_rerank_score,
            drift_warnings=row.drift_warnings or [],
        )
        for row in results
        if row.mode == "claim_evolution"
    ]


def _to_v1_telemetry(results: list[CaseResult], mode: str) -> list[V1CaseTelemetry]:
    return [
        V1CaseTelemetry(case_id=row.case_id, expectation=row.expectation, passed=row.passed, detail=row.detail)
        for row in results
        if row.mode == mode
    ]


def _build_report(
    mode: str,
    *,
    live: bool,
    concurrency: int,
    results: list[CaseResult],
) -> dict[str, Any]:
    passed_count = sum(1 for row in results if row.passed)
    evaluation_metrics: dict[str, Any] = {}

    if any(row.mode == "method_overlap" for row in results):
        evaluation_metrics["method_overlap"] = build_method_overlap_metrics(_to_method_overlap_telemetry(results))
    if any(row.mode == "claim_evolution" for row in results):
        evaluation_metrics["claim_evolution"] = build_claim_evolution_metrics(_to_claim_evolution_telemetry(results))
    if any(row.mode == "lens_clash" for row in results):
        evaluation_metrics["lens_clash"] = build_v1_mode_metrics(_to_v1_telemetry(results, "lens_clash"))
    if any(row.mode == "contradiction" for row in results):
        evaluation_metrics["contradiction"] = build_v1_mode_metrics(_to_v1_telemetry(results, "contradiction"))

    funnel_note = (
        "production embedding/reranker — full API funnel"
        if live
        else "stub scores / rule paths — validates funnel wiring without API cost"
    )

    return {
        "benchmark_id": f"patrol-{mode}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "mode": mode,
        "modes_executed": sorted({row.mode for row in results}),
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
                "live_coarse_score": row.live_coarse_score,
                "live_rerank_score": row.live_rerank_score,
                "drift_warnings": row.drift_warnings,
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
    parser = argparse.ArgumentParser(description="Patrol 四模式统一评估 Benchmark")
    parser.add_argument(
        "--mode",
        default="all",
        help=f"模式：all 或逗号分隔列表 ({','.join(PATROL_MODES)})",
    )
    parser.add_argument("--live", action="store_true", help="使用 live embedding / reranker（需 API 凭证）")
    parser.add_argument("--dry-run", action="store_true", help="Stub / 规则路径验证（默认行为）")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_DEFAULT_CONCURRENCY,
        help=f"最大并发数 (default: {_DEFAULT_CONCURRENCY}, env: {_CONCURRENCY_ENV})",
    )
    parser.add_argument("--output", type=Path, default=None, help="报告输出路径")
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        modes = parse_mode_list(args.mode)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return _EXIT_USAGE

    live = args.live and not args.dry_run
    concurrency = _resolve_concurrency(args.concurrency)
    get_settings.cache_clear()
    reset_embedding_client_cache()
    if live:
        from tests.fixtures.patrol_golden_config_snapshot import validate_golden_config_snapshot

        reset_embedding_client_cache()
        validate_golden_config_snapshot()

    all_results = await run_benchmark_modes(modes, live=live, concurrency=concurrency)
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
