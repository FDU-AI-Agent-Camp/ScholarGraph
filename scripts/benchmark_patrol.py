#!/usr/bin/env python
"""Patrol 金标回归脚本 (V2 Phase 3).

汇总 method_overlap 与 claim_evolution 金标对的 mock / live 门禁结果，
输出 JSON report 到 ``data/benchmark_reports/patrol-{timestamp}.json``。

Usage (from repo root)::

    uv run python scripts/benchmark_patrol.py
    uv run python scripts/benchmark_patrol.py --mode method_overlap --dry-run
    uv run python scripts/benchmark_patrol.py --mode claim_evolution --live

``--dry-run`` 仅校验金标文件与 mock 门禁（不调用 live embedding / reranker）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import get_settings  # noqa: E402
from backend.llm.embeddings import get_embedding_client, reset_embedding_client_cache  # noqa: E402
from backend.llm.reranker import RerankerClient  # noqa: E402
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair  # noqa: E402
from backend.patrol.method_overlap import build_method_overlap_insight  # noqa: E402
from backend.schemas.graph import GraphNode, NodeType  # noqa: E402
from backend.schemas.patrol import PatrolInsightStatus  # noqa: E402
from tests.fixtures.patrol_golden_set import (  # noqa: E402
    GoldenPairEmbeddingClient,
    GoldenPairExpectation,
    GoldenPairRerankerClient,
    load_patrol_golden_set,
)
from tests.fixtures.patrol_method_overlap_golden import (  # noqa: E402
    MethodOverlapGoldenExpectation,
    build_graphs_for_pair,
    load_method_overlap_golden_set,
)
from tests.patrol.test_method_overlap_functional import (  # noqa: E402
    _GoldenPcaEmbeddingClient,
    _NbLrNoiseEmbeddingClient,
)
from tests.patrol.test_patrol_method_overlap_golden_set import _DistinctLabelEmbeddingClient  # noqa: E402

EXIT_SUCCESS = 0
EXIT_FAILED = 1
_EXIT_USAGE = 2
_REPORT_DIR = _REPO_ROOT / "data" / "benchmark_reports"


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    mode: str
    expectation: str
    passed: bool
    detail: str


def _resolve_method_overlap_client(pair_id: str) -> Any:
    if pair_id == "stem-pos-01":
        return _GoldenPcaEmbeddingClient()
    if pair_id == "stem-neg-01":
        return _NbLrNoiseEmbeddingClient()
    return _DistinctLabelEmbeddingClient()


async def _run_method_overlap_case(*, live: bool) -> list[CaseResult]:
    results: list[CaseResult] = []
    golden = load_method_overlap_golden_set()
    settings = get_settings()

    for pair in golden.pairs:
        graphs = build_graphs_for_pair(pair)
        paper_ids = [pair.paper_a_id, pair.paper_b_id]
        if live and not settings.is_llm_mock:
            embedding_client = get_embedding_client()
        else:
            embedding_client = _resolve_method_overlap_client(pair.id)

        insight = await build_method_overlap_insight(
            graphs,
            paper_ids,
            embedding_client=embedding_client,
        )
        assert insight is not None

        if pair.expectation == MethodOverlapGoldenExpectation.POSITIVE:
            passed = insight.status == PatrolInsightStatus.READY and len(insight.structured_points) >= 1
            detail = f"status={insight.status.value}, points={len(insight.structured_points)}"
        else:
            passed = insight.status == PatrolInsightStatus.INSUFFICIENT_DATA and insight.structured_points == []
            detail = f"status={insight.status.value}"

        results.append(
            CaseResult(
                case_id=pair.id,
                mode="method_overlap",
                expectation=pair.expectation.value,
                passed=passed,
                detail=detail,
            )
        )
    return results


async def _run_claim_evolution_case(*, live: bool) -> list[CaseResult]:
    results: list[CaseResult] = []
    golden = load_patrol_golden_set()
    settings = get_settings()

    for pair in golden.pairs:
        left = GraphNode(id=f"{pair.id}-a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
        right = GraphNode(id=f"{pair.id}-b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})

        if live and not settings.is_llm_mock and settings.patrol_claim_rq_funnel_enabled():
            aligned = await align_research_question_pair(
                [left],
                [right],
                embedding_client=get_embedding_client(),
                settings=settings,
                reranker_client=RerankerClient(settings),
            )
        else:
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
        else:
            passed = aligned is None
            detail = "blocked" if aligned is None else "aligned"

        results.append(
            CaseResult(
                case_id=pair.id,
                mode="claim_evolution",
                expectation=pair.expectation.value,
                passed=passed,
                detail=detail,
            )
        )
    return results


def _build_report(mode: str, *, live: bool, results: list[CaseResult]) -> dict[str, Any]:
    passed_count = sum(1 for row in results if row.passed)
    return {
        "benchmark_id": f"patrol-{mode}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "mode": mode,
        "live": live,
        "dry_run": not live,
        "totals": {
            "cases": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "pass_rate": round(passed_count / len(results), 4) if results else 0.0,
        },
        "breakdown": [
            {
                "case_id": row.case_id,
                "mode": row.mode,
                "expectation": row.expectation,
                "passed": row.passed,
                "detail": row.detail,
            }
            for row in results
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patrol V2 金标回归")
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
        help="仅 mock 门禁（与默认相同，显式别名）",
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
    if live:
        reset_embedding_client_cache()

    modes = ["method_overlap", "claim_evolution"] if args.mode == "all" else [args.mode]
    all_results: list[CaseResult] = []
    for mode in modes:
        if mode == "method_overlap":
            all_results.extend(await _run_method_overlap_case(live=live))
        else:
            all_results.extend(await _run_claim_evolution_case(live=live))

    report = _build_report(args.mode, live=live, results=all_results)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or _REPORT_DIR / f"patrol-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["totals"], ensure_ascii=False))

    return EXIT_SUCCESS if report["totals"]["failed"] == 0 else EXIT_FAILED


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
