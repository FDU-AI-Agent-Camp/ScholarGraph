# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Report-layer contract tests for scripts/benchmark_qa.py (paradigm split + breakdown)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from tests.conftest import REPO_ROOT

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"
_GOLDEN_SET_PATH = REPO_ROOT / "data" / "qa_golden_set.json"


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa_report", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa_report"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mock_benchmark_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    get_settings.cache_clear()
    reset_llm_client_cache()
    yield graph_dir
    get_settings.cache_clear()
    reset_llm_client_cache()


def test_compute_paradigm_report_summary_mixed_dataset(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    items = [
        {"id": "hss-1", "paradigm": "HSS", "scale": "summary", "gold": {}},
        {"id": "stem-1", "paradigm": "STEM", "scale": "detail", "gold": {"paragraphs": ["p:chunk:1"]}},
        {"id": "stem-2", "paradigm": "STEM", "scale": "detail", "gold": {"paragraphs": ["p:chunk:2"]}},
    ]
    results = [
        {"evaluation": {"faithfulness": {"hallucination_rate": 0.0}}},
        {"evaluation": {"faithfulness": {"hallucination_rate": 0.0}, "completeness": {"chunk_recall": 1.0}}},
        {"evaluation": {"faithfulness": {"hallucination_rate": 0.0}, "completeness": {"chunk_recall": 0.5}}},
    ]
    summary = mod._compute_paradigm_report_summary(results, items)
    assert summary["total_cases"] == 3
    assert summary["hss_cases"] == 1
    assert summary["stem_cases"] == 2
    assert summary["global_hallucination_rate"] == 0.0
    assert summary["global_chunk_recall"] == 0.75


def test_build_report_breakdown_includes_matched_patterns(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    items = [
        {
            "id": "stem-001-q13",
            "paradigm": "STEM",
            "scale": "detail",
            "gold": {"required_patterns": ["78.5%", "ImageNet", "0.001"]},
        },
    ]
    results = [
        {
            "answer_text": "ImageNet top-1 accuracy 78.5% with learning rate 0.001.",
            "chunk_recall": 1.0,
        },
    ]
    breakdown = mod._build_report_breakdown(results, items)
    assert breakdown[0]["case_id"] == "stem-001-q13"
    assert breakdown[0]["paradigm"] == "STEM"
    assert breakdown[0]["scale"] == "DETAIL"
    assert breakdown[0]["chunk_recall"] == 1.0
    assert "78.5%" in breakdown[0]["required_patterns_matched"]
    assert "ImageNet" in breakdown[0]["required_patterns_matched"]


@pytest.mark.asyncio
async def test_full_mock_benchmark_report_paradigm_split(
    benchmark_qa_module: Any,
    mock_benchmark_env: Path,
    tmp_path: Path,
) -> None:
    mod = benchmark_qa_module
    os.environ["GRAPH_DATA_DIR"] = str(mock_benchmark_env)
    report_path = tmp_path / "benchmark_report.json"
    args = mod.parse_args(
        [
            "--golden-file",
            str(_GOLDEN_SET_PATH),
            "--graph-dir",
            str(mock_benchmark_env),
            "--concurrency",
            "4",
            "--output",
            str(report_path),
        ],
    )
    exit_code = await mod.run_benchmark(args)
    assert exit_code == mod.EXIT_SUCCESS

    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report["summary"]
    golden = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    items = golden["items"]
    hss_count = sum(1 for item in items if item["paradigm"] == "HSS")
    stem_count = sum(1 for item in items if item["paradigm"] == "STEM")

    assert report["total_questions"] == len(items)
    assert summary["total_cases"] == len(items)
    assert summary["hss_cases"] == hss_count
    assert summary["stem_cases"] == stem_count
    assert summary["global_hallucination_rate"] == 0.0
    assert summary["global_chunk_recall"] == 1.0
    assert summary["hallucination_pass"] is True

    assert isinstance(report["breakdown"], list)
    assert len(report["breakdown"]) == len(items)

    stem_rows = [row for row in report["breakdown"] if row["paradigm"] == "STEM" and row["scale"] == "DETAIL"]
    assert len(stem_rows) >= 2
    assert all(row.get("chunk_recall") == 1.0 for row in stem_rows)

    q13 = next(row for row in report["breakdown"] if row["case_id"] == "stem-001-q13")
    assert "78.5%" in q13["required_patterns_matched"]
    assert "ImageNet" in q13["required_patterns_matched"]
