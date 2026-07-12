"""Tests for QA_VERBOSITY_CEILING yellow-line warnings in benchmark_qa (non-blocking)."""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

import pytest
from tests.conftest import REPO_ROOT

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa_verbosity", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa_verbosity"] = module
    spec.loader.exec_module(module)
    return module


def test_maybe_flag_redundant_suspect_marks_high_verbosity(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    result: dict[str, Any] = {
        "question": "推导过程",
        "evaluation": {"directness": {"verbosity_rate": 0.984}},
    }
    flagged = mod._maybe_flag_redundant_suspect(
        result,
        verbosity_rate=0.984,
        question="推导过程",
    )
    assert flagged is True
    assert result["redundant_suspect"] is True
    assert result["verbosity_warning"] == mod._REDUNDANT_SUSPECT_TAG


def test_maybe_flag_redundant_suspect_skips_within_ceiling(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    result: dict[str, Any] = {
        "question": "简短回答",
        "evaluation": {"directness": {"verbosity_rate": 0.08}},
    }
    flagged = mod._maybe_flag_redundant_suspect(
        result,
        verbosity_rate=0.08,
        question="简短回答",
    )
    assert flagged is False
    assert "redundant_suspect" not in result


def test_collect_redundant_suspects_builds_summary(benchmark_qa_module: Any) -> None:
    mod = benchmark_qa_module
    results = [
        {
            "question": "q1",
            "redundant_suspect": True,
            "evaluation": {"directness": {"verbosity_rate": 0.95}},
        },
        {
            "question": "q2",
            "evaluation": {"directness": {"verbosity_rate": 0.05}},
        },
    ]
    suspects = mod._collect_redundant_suspects(results)
    assert len(suspects) == 1
    assert suspects[0]["question"] == "q1"
    assert suspects[0]["verbosity_rate"] == pytest.approx(0.95)
    assert suspects[0]["tag"] == mod._REDUNDANT_SUSPECT_TAG


def test_resolve_verbosity_ceiling_reads_env(
    benchmark_qa_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = benchmark_qa_module
    monkeypatch.setenv("QA_VERBOSITY_CEILING", "0.20")
    assert mod._resolve_verbosity_ceiling() == pytest.approx(0.20)
    monkeypatch.delenv("QA_VERBOSITY_CEILING", raising=False)
    assert mod._resolve_verbosity_ceiling() == pytest.approx(0.15)
