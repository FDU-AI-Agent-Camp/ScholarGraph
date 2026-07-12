"""Tests for QA router metrics in benchmark_qa.py."""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

import pytest
from tests.conftest import REPO_ROOT

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa_routing", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa_routing"] = module
    spec.loader.exec_module(module)
    return module


def test_compute_routing_summary_ttft_by_scale(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    items = [
        {"question": "q1", "scale": "summary", "paradigm": "HSS"},
        {"question": "q2", "scale": "detail", "paradigm": "HSS"},
    ]
    results = [
        {
            "detected_scale": "summary",
            "scale_routing_match": True,
            "ttft_ms": 10,
            "vector_branch_invoked": False,
            "graph_element_recall": 1.0,
            "numeric_match": True,
        },
        {
            "detected_scale": "detail",
            "scale_routing_match": True,
            "ttft_ms": 40,
            "vector_branch_invoked": True,
            "graph_element_recall": 1.0,
            "numeric_match": True,
        },
    ]
    summary = mod._compute_routing_summary(results, items)
    assert summary["mean_ttft_ms_summary"] == 10.0
    assert summary["mean_ttft_ms_detail"] == 40.0
    assert summary["summary_ttft_ratio_vs_detail"] == 4.0
    assert summary["scale_detection_accuracy"] == 1.0
    assert summary["vector_branch_wiring"]["wiring_pass"] is True


def test_detail_recall_gate_prefers_stem_detail_cohort(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    items = [
        {"question": "hss detail", "scale": "detail", "paradigm": "HSS", "gold": {}},
        {"question": "stem detail", "scale": "detail", "paradigm": "STEM", "gold": {}},
    ]
    results = [
        {"graph_element_recall": 0.5, "numeric_match": True},
        {"graph_element_recall": 1.0, "numeric_match": True},
    ]
    gate = mod._compute_detail_recall_gate(results, items)
    assert gate["cohort"] == "stem_detail"
    assert gate["count"] == 1
    assert gate["graph_element_recall_min"] == 1.0
    assert gate["recall_gate_pass"] is True


def test_detail_recall_gate_fails_when_recall_drops(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    items = [{"question": "detail", "scale": "detail", "paradigm": "HSS", "gold": {}}]
    results = [{"graph_element_recall": 0.8, "numeric_match": False}]
    gate = mod._compute_detail_recall_gate(results, items)
    assert gate["recall_gate_pass"] is False
    assert gate["numeric_gate_pass"] is False
