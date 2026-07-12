"""STEM numeric tolerance boundary tests (eval acceptance: decimal ↔ percent alignment).

Verifies extract_numbers_from_text + math.isclose guardrails for gold patterns like
``95.5%`` against equivalent decimal answers and perturbed percent variants.
"""

from __future__ import annotations

from typing import Any

import pytest
from backend.rag.models import QAJudgeResult, SentenceJudgment, SentenceLabel
from backend.rag.qa_heuristics import (
    extract_numbers_from_text,
    is_heuristic_hard_fuse_tripped,
    numeric_values_match,
    run_heuristic_guardrails,
)
from backend.rag.qa_judge import build_dual_track_evaluation

STEM_REL_TOL = 1e-3

_GOLD_ACCURACY_955: dict[str, Any] = {
    "nodes": [],
    "edges": [],
    "required_patterns": ["95.5%"],
    "forbidden_patterns": [],
    "numeric_rel_tol": STEM_REL_TOL,
}

_EXPECTED_DECIMAL = 0.955

_ANSWER_EQUIVALENT_DECIMAL = "准确率为 0.955。"
_ANSWER_EQUIVALENT_PERCENT = "Accuracy: 95.5%。"
_ANSWER_SMALL_PERTURBATION = "Accuracy: 95.49%。"
_ANSWER_LARGE_PERTURBATION = "Accuracy: 95.4%。"


@pytest.fixture
def gold_accuracy_955() -> dict[str, Any]:
    return dict(_GOLD_ACCURACY_955)


def test_extract_numbers_aligns_decimal_and_percent_forms() -> None:
    """Extraction must normalize 95.5% → 0.955 and read bare decimals as-is."""
    from_decimal = extract_numbers_from_text(_ANSWER_EQUIVALENT_DECIMAL)
    from_percent_gold = extract_numbers_from_text("Accuracy: 95.5%")
    from_perturbed = extract_numbers_from_text(_ANSWER_SMALL_PERTURBATION)

    assert _EXPECTED_DECIMAL in from_decimal
    assert _EXPECTED_DECIMAL in from_percent_gold
    assert pytest.approx(0.9549) in from_perturbed


@pytest.mark.parametrize(
    ("candidate", "should_match"),
    [
        (_EXPECTED_DECIMAL, True),
        (0.955, True),
        (0.9549, True),
        (0.954, False),
    ],
    ids=["gold-decimal", "answer-decimal", "answer-95.49pct", "answer-95.4pct-rejected"],
)
def test_math_isclose_rel_tol_1e3_stem_boundary(candidate: float, should_match: bool) -> None:
    """rel_tol=1e-3: equivalent 0.955 passes; 95.49% (0.9549) still within isclose; 95.4% fails."""
    assert numeric_values_match(_EXPECTED_DECIMAL, candidate, rel_tol=STEM_REL_TOL) is should_match


def test_guardrails_passes_equivalent_decimal_answer(gold_accuracy_955: dict[str, Any]) -> None:
    result = run_heuristic_guardrails(
        _ANSWER_EQUIVALENT_DECIMAL,
        [],
        gold_accuracy_955,
        paradigm="STEM",
    )
    assert 0.955 in result.extracted_numbers
    assert result.numeric_match is True
    assert result.missing_numbers == []
    assert is_heuristic_hard_fuse_tripped(result) is False


def test_guardrails_passes_exact_percent_answer(gold_accuracy_955: dict[str, Any]) -> None:
    result = run_heuristic_guardrails(
        _ANSWER_EQUIVALENT_PERCENT,
        [],
        gold_accuracy_955,
        paradigm="STEM",
    )
    assert result.numeric_match is True
    assert is_heuristic_hard_fuse_tripped(result) is False


def test_guardrails_rejects_perturbation_beyond_rel_tol_1e3(gold_accuracy_955: dict[str, Any]) -> None:
    """95.4% (~0.1 pp below gold) exceeds rel_tol=1e-3 → numeric hard fuse trips."""
    result = run_heuristic_guardrails(
        _ANSWER_LARGE_PERTURBATION,
        [],
        gold_accuracy_955,
        paradigm="STEM",
    )
    assert any(pytest.approx(0.954, rel=1e-9) == value for value in result.extracted_numbers)
    assert result.numeric_match is False
    assert _EXPECTED_DECIMAL in result.missing_numbers
    assert is_heuristic_hard_fuse_tripped(result) is True


def test_guardrails_95_49_percent_within_rel_tol_1e3_passes(gold_accuracy_955: dict[str, Any]) -> None:
    """95.49% (0.9549) is within math.isclose rel_tol=1e-3 of 0.955 — documents IEEE semantics."""
    result = run_heuristic_guardrails(
        _ANSWER_SMALL_PERTURBATION,
        [],
        gold_accuracy_955,
        paradigm="STEM",
    )
    assert pytest.approx(0.9549) in result.extracted_numbers
    assert result.numeric_match is True


def test_guardrails_95_49_percent_rejected_under_stricter_rel_tol_1e4() -> None:
    """Tightening rel_tol alone is a blunt instrument — prefer numeric_abs_tol for product tuning."""
    strict_gold = {
        **_GOLD_ACCURACY_955,
        "numeric_rel_tol": 1e-4,
    }
    result = run_heuristic_guardrails(
        _ANSWER_SMALL_PERTURBATION,
        [],
        strict_gold,
        paradigm="STEM",
    )
    assert result.numeric_match is False
    assert is_heuristic_hard_fuse_tripped(result) is True


def test_product_numeric_abs_tol_5e4_allows_half_percent_point_band() -> None:
    """numeric_abs_tol=5e-4 accepts 95.49% (|0.955-0.9549|=0.0001 < 0.0005) with rel_tol=1e-3."""
    product_gold = {
        **_GOLD_ACCURACY_955,
        "numeric_rel_tol": STEM_REL_TOL,
        "numeric_abs_tol": 5e-4,
    }
    result = run_heuristic_guardrails(
        _ANSWER_SMALL_PERTURBATION,
        [],
        product_gold,
        paradigm="STEM",
    )
    assert result.numeric_match is True
    assert is_heuristic_hard_fuse_tripped(result) is False


def test_numeric_abs_tol_protects_small_p_value_from_rel_only_false_reject() -> None:
    """p-value 0.0051 vs gold 0.005: rel_tol=1e-3 alone rejects; abs_tol=1e-3 dual gate accepts."""
    gold = {
        "nodes": [],
        "edges": [],
        "required_patterns": ["0.005"],
        "forbidden_patterns": [],
        "numeric_rel_tol": 1e-3,
        "numeric_abs_tol": 1e-3,
    }
    assert numeric_values_match(0.005, 0.0051, rel_tol=1e-3, abs_tol=1e-9) is False
    assert numeric_values_match(0.005, 0.0051, rel_tol=1e-3, abs_tol=1e-3) is True

    result = run_heuristic_guardrails(
        "统计显著性 p-value = 0.0051。",
        [],
        gold,
        paradigm="STEM",
    )
    assert result.numeric_match is True


def test_expected_numbers_entry_abs_tol_overrides_gold_default() -> None:
    gold = {
        "nodes": [],
        "edges": [],
        "required_patterns": [],
        "forbidden_patterns": [],
        "numeric_rel_tol": 1e-3,
        "numeric_abs_tol": 1e-9,
        "expected_numbers": [{"value": "0.005", "abs_tol": 1e-3}],
    }
    result = run_heuristic_guardrails("p = 0.0051", [], gold, paradigm="STEM")
    assert result.numeric_match is True


def test_numeric_fuse_trips_dual_track_hallucination_rate(gold_accuracy_955: dict[str, Any]) -> None:
    """Failed numeric gate must fuse to hallucination_rate=100% even when Judge clears."""
    guardrails = run_heuristic_guardrails(
        _ANSWER_LARGE_PERTURBATION,
        [],
        gold_accuracy_955,
        paradigm="STEM",
    )
    judge = QAJudgeResult(
        sentence_judgments=[
            SentenceJudgment(sentence=_ANSWER_LARGE_PERTURBATION, label=SentenceLabel.SUPPORTED),
        ],
        factual_consistency=1.0,
        hallucination_detected=False,
        reasoning="Judge missed numeric mismatch.",
    )
    evaluation = build_dual_track_evaluation(guardrails, judge)
    assert evaluation["faithfulness"]["hallucination_rate"] == 1.0
    assert evaluation["dual_track"]["heuristic_hard_fuse_tripped"] is True
    assert evaluation["dual_track"]["judge_hallucination_detected"] is False
