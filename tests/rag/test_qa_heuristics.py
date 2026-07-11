"""Tests for dual-track heuristic guardrails (Track A)."""

from __future__ import annotations

import pytest

from backend.rag.qa_heuristics import (
    compute_verbosity_rate,
    derive_golden_reference_text,
    extract_datasets_from_text,
    extract_numbers_from_text,
    numeric_values_match,
    run_heuristic_guardrails,
)


def test_forbidden_pattern_trips_guardrail() -> None:
    result = run_heuristic_guardrails(
        "回答包含 PCR 检测方法",
        [],
        {"required_patterns": [], "forbidden_patterns": ["PCR"], "nodes": [], "edges": []},
    )
    assert result.forbidden_tripped is True
    assert result.passed is False


def test_numeric_expectation_from_required_patterns() -> None:
    result = run_heuristic_guardrails(
        "实验 F1 达到 0.89，在 ImageNet 上验证。",
        [],
        {
            "required_patterns": ["0.89", "F1", "ImageNet"],
            "forbidden_patterns": [],
            "nodes": [],
            "edges": [],
        },
    )
    assert result.numeric_match is True
    assert result.dataset_match is True
    assert result.passed is True
    assert 0.89 in result.extracted_numbers


def test_numeric_tolerance_allows_small_delta() -> None:
    result = run_heuristic_guardrails(
        "准确率达到 0.891",
        [],
        {
            "required_patterns": [],
            "forbidden_patterns": [],
            "expected_numbers": [{"value": 0.89, "abs_tol": 0.01}],
            "nodes": [],
            "edges": [],
        },
    )
    assert result.numeric_match is True
    assert result.missing_numbers == []


def test_missing_numeric_fails_guardrail() -> None:
    result = run_heuristic_guardrails(
        "方法描述充分但未报告数值。",
        [],
        {
            "required_patterns": ["0.89"],
            "forbidden_patterns": [],
            "nodes": [],
            "edges": [],
        },
    )
    assert result.numeric_match is False
    assert result.missing_numbers == [0.89]
    assert result.passed is False


def test_extract_numbers_and_datasets_helpers() -> None:
    assert 0.89 in extract_numbers_from_text("F1=0.89 on CIFAR-10")
    assert 0.15 in extract_numbers_from_text("accuracy 15% on test set")
    assert "CIFAR-10" in extract_datasets_from_text("Evaluated on CIFAR-10 and MNIST")


def test_percent_gold_matches_decimal_and_percent_answer() -> None:
    result = run_heuristic_guardrails(
        "模型准确率达到 15%，在 ImageNet 上验证。",
        [],
        {
            "required_patterns": ["15%"],
            "forbidden_patterns": [],
            "nodes": [],
            "edges": [],
        },
    )
    assert result.numeric_match is True
    assert result.missing_numbers == []


def test_math_isclose_handles_trailing_zeros() -> None:
    assert numeric_values_match(0.15, 0.150, rel_tol=0.01)
    assert numeric_values_match(0.89, 0.891, rel_tol=0.01)


def test_verbosity_rate_uses_character_inflation_heuristic() -> None:
    gold = {"required_patterns": ["0.89", "ImageNet"]}
    golden_text = derive_golden_reference_text(gold)
    short_answer = golden_text
    long_answer = short_answer * 3

    assert compute_verbosity_rate(short_answer, gold) == 0.0
    assert compute_verbosity_rate(long_answer, gold) == pytest.approx(1.0 - 1 / 3, rel=1e-4)


def test_verbosity_rate_prefers_explicit_reference_answer() -> None:
    gold = {
        "reference_answer": "F1 0.89 on ImageNet",
        "required_patterns": ["ignored when reference present"],
    }
    reference = "F1 0.89 on ImageNet"
    assert compute_verbosity_rate(reference, gold) == 0.0
    assert compute_verbosity_rate(reference + reference, gold) == pytest.approx(0.5, rel=1e-4)


def test_stem_paradigm_aligned_requires_numeric_and_dataset() -> None:
    result = run_heuristic_guardrails(
        "方法描述充分但未报告数值。",
        [],
        {
            "required_patterns": ["0.89", "ImageNet"],
            "forbidden_patterns": [],
            "nodes": [],
            "edges": [],
        },
        paradigm="STEM",
    )
    assert result.paradigm_aligned is False
    assert result.passed is False


def test_hss_paradigm_aligned_requires_required_patterns() -> None:
    result = run_heuristic_guardrails(
        "回答未包含金标术语。",
        [],
        {
            "required_patterns": ["核心论点"],
            "forbidden_patterns": [],
            "nodes": [],
            "edges": [],
        },
        paradigm="HSS",
    )
    assert result.paradigm_aligned is False
