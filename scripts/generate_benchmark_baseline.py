#!/usr/bin/env python3
"""Build or refresh committed dual(rules) regression baseline from a batch report.

Usage (repo root):
    uv run python scripts/generate_benchmark_baseline.py
    uv run python scripts/generate_benchmark_baseline.py --report \\
        data/benchmark_reports/corpus-batch-20260604-162832.json
    uv run python scripts/generate_benchmark_baseline.py --compare
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark_regression import (  # noqa: E402
    build_baseline_from_report,
    compare_report_to_baseline,
    write_baseline,
)

REPORT_DIR = REPO_ROOT / "data" / "benchmark_reports"
DEFAULT_BASELINE_ID = "phase-d-dual-rules"


def _latest_report() -> Path | None:
    reports = sorted(REPORT_DIR.glob("corpus-batch-*.json"))
    return reports[-1] if reports else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        help="Full corpus-batch JSON (default: latest under data/benchmark_reports/)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare report to existing committed baseline instead of writing",
    )
    parser.add_argument(
        "--baseline-id",
        default=DEFAULT_BASELINE_ID,
        help="baseline_id field for new baseline payload",
    )
    args = parser.parse_args()

    report_path = args.report or _latest_report()
    if report_path is None or not report_path.is_file():
        print("No corpus-batch report found. Run:", file=sys.stderr)
        print("  uv run python scripts/benchmark_dual_route.py --all-corpus", file=sys.stderr)
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))

    if args.compare:
        result = compare_report_to_baseline(report)
        print(result.format_message())
        return 0 if result.ok else 1

    payload = build_baseline_from_report(
        report,
        baseline_id=args.baseline_id,
        source_report=report_path.name,
    )
    out = write_baseline(payload)
    print(f"Baseline written: {out}")
    print(f"dual(rules) total: {payload['totals']['dual_route_rules']}/{payload['totals']['max']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
