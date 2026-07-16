"""Critical boundary tests for chunk_recall gate float comparisons."""

from __future__ import annotations

import importlib.util
import math
import sys
from typing import Any

import pytest
from backend.rag.qa_heuristics import chunk_recall_meets_floor, compute_chunk_recall
from tests.conftest import REPO_ROOT

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"
_FLOOR = 0.5
_CHUNK_COHORT_SIZE = 100
_HIT_COUNT_FAIL = 49
_HIT_COUNT_PASS = 50


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa_gate_bounds", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa_gate_bounds"] = module
    spec.loader.exec_module(module)
    return module


def _gold_with_n_chunks(count: int) -> dict[str, list[str]]:
    return {"paragraphs": [f"stem-001:chunk:{index}" for index in range(count)]}


def _chunk_citations(count: int) -> list[dict[str, str]]:
    return [{"type": "chunk", "chunk_id": f"stem-001:chunk:{index}"} for index in range(count)]


def _stem_detail_item(*, scale: str = "detail", paradigm: str = "STEM", gold: dict | None = None) -> dict[str, Any]:
    return {
        "question": "detail question",
        "scale": scale,
        "paradigm": paradigm,
        "gold": gold or _gold_with_n_chunks(_CHUNK_COHORT_SIZE),
    }


def _result_with_chunk_recall(recall: float) -> dict[str, Any]:
    return {
        "graph_element_recall": 1.0,
        "numeric_match": True,
        "chunk_recall": recall,
    }


def test_chunk_recall_meets_floor_handles_ieee_boundary() -> None:
    assert chunk_recall_meets_floor(0.5, _FLOOR) is True
    assert chunk_recall_meets_floor(0.49, _FLOOR) is False
    assert chunk_recall_meets_floor(0.5 - 1e-8, _FLOOR) is False
    assert chunk_recall_meets_floor(0.5 - 1e-10, _FLOOR) is True
    almost_half = 0.5 + math.ulp(0.5)
    assert chunk_recall_meets_floor(almost_half, _FLOOR) is True


def test_compute_chunk_recall_fails_one_point_below_half(benchmark_qa_module: Any) -> None:
    gold = _gold_with_n_chunks(_CHUNK_COHORT_SIZE)
    citations = _chunk_citations(_HIT_COUNT_FAIL)
    recall = compute_chunk_recall(citations, gold)
    assert recall == pytest.approx(0.49, abs=1e-12)
    assert recall is not None
    assert chunk_recall_meets_floor(recall, _FLOOR) is False

    gate = benchmark_qa_module._compute_detail_recall_gate(
        [_result_with_chunk_recall(recall)],
        [_stem_detail_item(gold=gold)],
        chunk_recall_floor=_FLOOR,
    )
    assert gate["chunk_recall_gate_pass"] is False
    assert gate["chunk_recall_min"] == pytest.approx(0.49, abs=1e-12)

    policy = benchmark_qa_module.ChunkRecallGatePolicy(floor=_FLOOR, tier="mock_dry_run", enforced=True)
    assert benchmark_qa_module._should_fail_chunk_recall_gate(policy, gate) is True


def test_compute_chunk_recall_passes_exact_half_floor(benchmark_qa_module: Any) -> None:
    gold = _gold_with_n_chunks(_CHUNK_COHORT_SIZE)
    citations = _chunk_citations(_HIT_COUNT_PASS)
    recall = compute_chunk_recall(citations, gold)
    assert recall == pytest.approx(0.5, abs=1e-12)
    assert chunk_recall_meets_floor(recall, _FLOOR) is True

    gate = benchmark_qa_module._compute_detail_recall_gate(
        [_result_with_chunk_recall(recall)],
        [_stem_detail_item(gold=gold)],
        chunk_recall_floor=_FLOOR,
    )
    assert gate["chunk_recall_gate_pass"] is True
    assert gate["chunk_recall_min"] == pytest.approx(0.5, abs=1e-12)

    policy = benchmark_qa_module.ChunkRecallGatePolicy(floor=_FLOOR, tier="mock_dry_run", enforced=True)
    assert benchmark_qa_module._should_fail_chunk_recall_gate(policy, gate) is False


def test_empty_paragraph_gold_is_exempt_with_lossless_default(benchmark_qa_module: Any) -> None:
    empty_gold: dict[str, list[str]] = {"nodes": ["n_thesis"], "edges": [], "paragraphs": []}
    for _ in range(100):
        assert compute_chunk_recall([], empty_gold) == 1.0

    hss_item = _stem_detail_item(scale="detail", paradigm="HSS", gold=empty_gold)
    gate = benchmark_qa_module._compute_detail_recall_gate(
        [_result_with_chunk_recall(1.0)],
        [hss_item],
        chunk_recall_floor=_FLOOR,
    )
    assert gate["chunk_recall_cohort_count"] == 0
    assert gate["chunk_recall_gate_pass"] is True
    assert gate["chunk_recall_min"] is None

    policy = benchmark_qa_module.ChunkRecallGatePolicy(floor=_FLOOR, tier="mock_dry_run", enforced=True)
    assert benchmark_qa_module._should_fail_chunk_recall_gate(policy, gate) is False
