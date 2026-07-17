# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""T6 smoke: fast benchmark regression sanity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "benchmark" / "dual_rules_baseline.json"
REGRESSION_SCRIPT = REPO_ROOT / "scripts" / "benchmark_regression.py"
GENERATE_SCRIPT = REPO_ROOT / "scripts" / "generate_benchmark_baseline.py"


@pytest.mark.smoke
def test_smoke_benchmark_regression_scripts_exist() -> None:
    assert REGRESSION_SCRIPT.is_file()
    assert GENERATE_SCRIPT.is_file()
    assert BASELINE_PATH.is_file()


@pytest.mark.smoke
def test_smoke_load_baseline_default_path(benchmark_regression_module) -> None:
    baseline = benchmark_regression_module.load_baseline()
    assert baseline["baseline_id"] == "phase-d-dual-rules"
    assert baseline["totals"]["dual_route_rules"] == 46


@pytest.mark.smoke
def test_smoke_baseline_json_parseable() -> None:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert len(payload["paper_ids"]) == 17
    assert payload["constraints"]["dual_gte_pymupdf"] is True
