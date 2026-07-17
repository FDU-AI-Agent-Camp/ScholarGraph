# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for patrol benchmark evaluation metrics."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.benchmark_patrol_metrics import (  # noqa: E402
    ClaimEvolutionCaseTelemetry,
    MethodOverlapCaseTelemetry,
    build_claim_evolution_metrics,
    build_method_overlap_margin_distribution,
    build_method_overlap_precision_recall,
)


def _method_case(
    *,
    case_id: str,
    golden_polarity: str,
    expected_match_type: str | None,
    passed: bool,
    actual_status: str | None,
    actual_match_type: str | None,
    overlap_score: float | None,
    theta_min: float | None,
    prescreen_cosine: float | None,
    semantic_threshold: float = 0.88,
    semantic_prescreen_alarm: bool = False,
) -> MethodOverlapCaseTelemetry:
    return MethodOverlapCaseTelemetry(
        case_id=case_id,
        archetype="TEST",
        golden_polarity=golden_polarity,  # type: ignore[arg-type]
        expected_match_type=expected_match_type,
        passed=passed,
        actual_status=actual_status,
        actual_match_type=actual_match_type,
        overlap_score=overlap_score,
        theta_min=theta_min,
        prescreen_cosine=prescreen_cosine,
        semantic_threshold=semantic_threshold,
        path_family="blocked_clean",
        semantic_prescreen_alarm=semantic_prescreen_alarm,
        drift_passed=None,
    )


def test_method_overlap_precision_recall_decouples_paths() -> None:
    cases = [
        _method_case(
            case_id="literal-tp",
            golden_polarity="positive",
            expected_match_type="LITERAL",
            passed=True,
            actual_status="READY",
            actual_match_type="literal",
            overlap_score=1.0,
            theta_min=1.0,
            prescreen_cosine=0.5,
        ),
        _method_case(
            case_id="semantic-tp",
            golden_polarity="positive",
            expected_match_type="SEMANTIC",
            passed=True,
            actual_status="READY",
            actual_match_type="semantic",
            overlap_score=0.95,
            theta_min=0.88,
            prescreen_cosine=0.92,
        ),
        _method_case(
            case_id="semantic-fp-alarm",
            golden_polarity="negative",
            expected_match_type=None,
            passed=True,
            actual_status="INSUFFICIENT_DATA",
            actual_match_type=None,
            overlap_score=None,
            theta_min=None,
            prescreen_cosine=0.9,
            semantic_prescreen_alarm=True,
        ),
    ]

    metrics = build_method_overlap_precision_recall(cases)

    assert metrics["literal"]["tp"] == 1
    assert metrics["literal"]["recall"] == 1.0
    assert metrics["semantic"]["tp"] == 1
    assert metrics["semantic"]["recall"] == 1.0
    assert metrics["semantic_false_positive_rate"] == 1.0
    assert metrics["semantic_prescreen_alarms"] == 1


def test_margin_distribution_suggests_threshold_and_margins() -> None:
    cases = [
        _method_case(
            case_id="semantic-tp",
            golden_polarity="positive",
            expected_match_type="SEMANTIC",
            passed=True,
            actual_status="READY",
            actual_match_type="semantic",
            overlap_score=0.95,
            theta_min=0.88,
            prescreen_cosine=0.92,
        ),
        _method_case(
            case_id="neg",
            golden_polarity="negative",
            expected_match_type=None,
            passed=True,
            actual_status="INSUFFICIENT_DATA",
            actual_match_type=None,
            overlap_score=None,
            theta_min=None,
            prescreen_cosine=0.82,
            semantic_prescreen_alarm=False,
        ),
    ]

    margin = build_method_overlap_margin_distribution(cases)

    assert margin["true_positive_overlap_scores"][0]["margin"] == 0.07
    assert margin["false_positive_prescreen_cosines"][0]["safety_margin"] == 0.06
    assert margin["margin_summary"]["suggested_semantic_threshold"] == 0.87
    assert margin["margin_summary"]["true_positive_min_overlap_margin"] == 0.07
    assert margin["margin_summary"]["negative_min_safety_margin"] == 0.06


def test_claim_evolution_confusion_matrix() -> None:
    cases = [
        ClaimEvolutionCaseTelemetry("pos-1", "positive", True, 0.9, 0.8),  # type: ignore[arg-type]
        ClaimEvolutionCaseTelemetry("neg-1", "negative", True, 0.2, 0.1),  # type: ignore[arg-type]
        ClaimEvolutionCaseTelemetry("pos-2", "positive", False, 0.4, 0.3),  # type: ignore[arg-type]
    ]
    metrics = build_claim_evolution_metrics(cases)

    assert metrics["confusion"]["tp"] == 1
    assert metrics["confusion"]["fn"] == 1
    assert metrics["confusion"]["tn"] == 1
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 0.5
