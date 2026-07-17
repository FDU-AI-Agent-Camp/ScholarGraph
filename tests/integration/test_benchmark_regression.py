# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""T6 integration: benchmark report ↔ baseline round-trip and CLI scripts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "benchmark" / "dual_rules_baseline.json"
PHASE_D_REPORT = REPO_ROOT / "data" / "benchmark_reports" / "corpus-batch-20260604-162832.json"
GENERATE_BASELINE_SCRIPT = REPO_ROOT / "scripts" / "generate_benchmark_baseline.py"
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_dual_route.py"


@pytest.mark.integration
def test_phase_d_report_round_trips_through_baseline_builder(benchmark_regression_module) -> None:
    if not PHASE_D_REPORT.is_file():
        pytest.skip("缺少 Phase D 报告 corpus-batch-20260604-162832.json")

    mod = benchmark_regression_module
    report = json.loads(PHASE_D_REPORT.read_text(encoding="utf-8"))
    rebuilt = mod.build_baseline_from_report(
        report,
        baseline_id="phase-d-dual-rules",
        source_report=PHASE_D_REPORT.name,
    )
    assert rebuilt["totals"]["dual_route_rules"] == 46
    assert rebuilt["totals"]["max"] == 68
    assert len(rebuilt["paper_ids"]) == 17

    result = mod.compare_report_to_baseline(report, rebuilt)
    assert result.ok, result.format_message()


@pytest.mark.integration
def test_generate_benchmark_baseline_compare_cli_exits_zero() -> None:
    if not PHASE_D_REPORT.is_file():
        pytest.skip("缺少 Phase D 报告 corpus-batch-20260604-162832.json")

    result = subprocess.run(
        [
            sys.executable,
            str(GENERATE_BASELINE_SCRIPT),
            "--compare",
            "--report",
            str(PHASE_D_REPORT),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "46/68" in result.stdout


@pytest.mark.integration
def test_benchmark_dual_route_imports_regression_helpers(benchmark_dual_route_module) -> None:
    mod = benchmark_dual_route_module
    assert callable(mod.compare_report_to_baseline)
    assert callable(mod.build_baseline_from_report)
    assert callable(mod.persist_baseline)


@pytest.mark.integration
def test_committed_baseline_matches_phase_d_report_when_present(benchmark_regression_module) -> None:
    if not PHASE_D_REPORT.is_file():
        pytest.skip("缺少 Phase D 报告 corpus-batch-20260604-162832.json")

    mod = benchmark_regression_module
    report = json.loads(PHASE_D_REPORT.read_text(encoding="utf-8"))
    baseline = mod.load_baseline(BASELINE_PATH)
    result = mod.compare_report_to_baseline(report, baseline)
    assert result.ok, result.format_message()
