# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Pure metric builders for ``scripts/benchmark_patrol.py`` evaluation reports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

GoldenPolarity = Literal["positive", "negative"]
PathFamily = Literal["literal", "semantic", "blocked_clean", "semantic_prescreen_alarm", "none"]


@dataclass(frozen=True, slots=True)
class MethodOverlapCaseTelemetry:
    """Per-case telemetry consumed by the evaluation metrics matrix."""

    case_id: str
    archetype: str
    golden_polarity: GoldenPolarity
    expected_match_type: str | None
    passed: bool
    actual_status: str | None
    actual_match_type: str | None
    overlap_score: float | None
    theta_min: float | None
    prescreen_cosine: float | None
    semantic_threshold: float
    path_family: PathFamily
    semantic_prescreen_alarm: bool
    drift_passed: bool | None


@dataclass(frozen=True, slots=True)
class ClaimEvolutionCaseTelemetry:
    """Per-case telemetry for claim_evolution pass-rate / precision matrix."""

    case_id: str
    golden_polarity: GoldenPolarity
    passed: bool
    coarse_score: float | None
    rerank_score: float | None
    live_coarse_score: float | None = None
    live_rerank_score: float | None = None
    drift_warnings: list[str] | None = None


@dataclass(frozen=True, slots=True)
class V1CaseTelemetry:
    """Per-case telemetry for V1 lens_clash / contradiction golden cases."""

    case_id: str
    expectation: str
    passed: bool
    detail: str


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _status_ready(actual_status: str | None) -> bool:
    return (actual_status or "").upper() == "READY"


def _path_counts(
    cases: Sequence[MethodOverlapCaseTelemetry],
    *,
    expected_match_type: str,
) -> dict[str, int]:
    subset = [row for row in cases if row.expected_match_type == expected_match_type]
    tp = sum(
        1
        for row in subset
        if row.golden_polarity == "positive"
        and _status_ready(row.actual_status)
        and row.actual_match_type == expected_match_type.lower()
    )
    fn = sum(1 for row in subset if row.golden_polarity == "positive" and not row.passed)
    fp = sum(
        1
        for row in cases
        if row.golden_polarity == "negative"
        and _status_ready(row.actual_status)
        and row.actual_match_type == expected_match_type.lower()
    )
    return {"tp": tp, "fp": fp, "fn": fn}


def build_method_overlap_precision_recall(
    cases: Sequence[MethodOverlapCaseTelemetry],
) -> dict[str, Any]:
    """Decouple literal vs semantic precision/recall and semantic false-positive rate."""
    literal = _path_counts(cases, expected_match_type="LITERAL")
    semantic = _path_counts(cases, expected_match_type="SEMANTIC")

    literal_precision = _safe_ratio(literal["tp"], literal["tp"] + literal["fp"])
    literal_recall = _safe_ratio(literal["tp"], literal["tp"] + literal["fn"])
    semantic_precision = _safe_ratio(semantic["tp"], semantic["tp"] + semantic["fp"])
    semantic_recall = _safe_ratio(semantic["tp"], semantic["tp"] + semantic["fn"])

    negative_cases = [row for row in cases if row.golden_polarity == "negative"]
    semantic_alarms = sum(1 for row in negative_cases if row.semantic_prescreen_alarm)
    semantic_false_positive_rate = _safe_ratio(semantic_alarms, len(negative_cases))

    return {
        "literal": {
            **literal,
            "precision": literal_precision,
            "recall": literal_recall,
        },
        "semantic": {
            **semantic,
            "precision": semantic_precision,
            "recall": semantic_recall,
        },
        "semantic_false_positive_rate": semantic_false_positive_rate,
        "semantic_prescreen_alarms": semantic_alarms,
        "negative_cases": len(negative_cases),
    }


def build_method_overlap_margin_distribution(
    cases: Sequence[MethodOverlapCaseTelemetry],
) -> dict[str, Any]:
    """Score distributions for true positives and false-positive archetypes."""
    true_positive_rows = [
        row
        for row in cases
        if row.golden_polarity == "positive" and _status_ready(row.actual_status) and row.overlap_score is not None
    ]
    negative_rows = [row for row in cases if row.golden_polarity == "negative" and row.prescreen_cosine is not None]

    overlap_margins = [
        {
            "case_id": row.case_id,
            "overlap_score": _round4(row.overlap_score),
            "theta_min": _round4(row.theta_min),
            "margin": _round4((row.overlap_score or 0.0) - (row.theta_min or 0.0)),
            "match_type": row.actual_match_type,
        }
        for row in true_positive_rows
        if row.theta_min is not None and row.overlap_score is not None
    ]

    prescreen_margins = [
        {
            "case_id": row.case_id,
            "prescreen_cosine": _round4(row.prescreen_cosine),
            "semantic_threshold": _round4(row.semantic_threshold),
            "safety_margin": _round4(row.semantic_threshold - (row.prescreen_cosine or 0.0)),
            "semantic_prescreen_alarm": row.semantic_prescreen_alarm,
        }
        for row in negative_rows
    ]

    positive_prescreen = [
        row.prescreen_cosine
        for row in cases
        if row.golden_polarity == "positive"
        and row.expected_match_type == "SEMANTIC"
        and row.prescreen_cosine is not None
    ]
    negative_prescreen = [row.prescreen_cosine for row in negative_rows if row.prescreen_cosine is not None]

    suggested_threshold: float | None = None
    if positive_prescreen and negative_prescreen:
        min_positive = min(positive_prescreen)
        max_negative = max(negative_prescreen)
        suggested_threshold = _round4((min_positive + max_negative) / 2.0)

    margin_summary: dict[str, float | None] = {
        "true_positive_min_overlap_margin": None,
        "negative_min_safety_margin": None,
        "suggested_semantic_threshold": suggested_threshold,
    }
    if overlap_margins:
        margins = [entry["margin"] for entry in overlap_margins if entry["margin"] is not None]
        if margins:
            margin_summary["true_positive_min_overlap_margin"] = min(margins)
    if prescreen_margins:
        safety = [entry["safety_margin"] for entry in prescreen_margins if entry["safety_margin"] is not None]
        if safety:
            margin_summary["negative_min_safety_margin"] = min(safety)

    return {
        "true_positive_overlap_scores": overlap_margins,
        "false_positive_prescreen_cosines": prescreen_margins,
        "margin_summary": margin_summary,
    }


def build_method_overlap_metrics(cases: Sequence[MethodOverlapCaseTelemetry]) -> dict[str, Any]:
    """Aggregate method_overlap evaluation matrix."""
    drift_guard_cases = [row for row in cases if row.drift_passed is not None]
    drift_passed = sum(1 for row in drift_guard_cases if row.drift_passed)
    return {
        "precision_recall": build_method_overlap_precision_recall(cases),
        "margin_distribution": build_method_overlap_margin_distribution(cases),
        "drift_guard": {
            "cases": len(drift_guard_cases),
            "passed": drift_passed,
            "failed": len(drift_guard_cases) - drift_passed,
        },
    }


def build_claim_evolution_metrics(cases: Sequence[ClaimEvolutionCaseTelemetry]) -> dict[str, Any]:
    """Binary precision/recall for claim_evolution golden pairs."""
    tp = sum(1 for row in cases if row.golden_polarity == "positive" and row.passed)
    fp = sum(1 for row in cases if row.golden_polarity == "negative" and not row.passed)
    fn = sum(1 for row in cases if row.golden_polarity == "positive" and not row.passed)
    tn = sum(1 for row in cases if row.golden_polarity == "negative" and row.passed)

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    pass_rate = _safe_ratio(sum(1 for row in cases if row.passed), len(cases))

    mock_margins = [
        {
            "case_id": row.case_id,
            "coarse_score": _round4(row.coarse_score),
            "rerank_score": _round4(row.rerank_score),
            "live_coarse_score": _round4(row.live_coarse_score),
            "live_rerank_score": _round4(row.live_rerank_score),
            "golden_polarity": row.golden_polarity,
            "drift_warnings": row.drift_warnings or [],
        }
        for row in cases
        if row.coarse_score is not None
        or row.rerank_score is not None
        or row.live_coarse_score is not None
        or row.live_rerank_score is not None
    ]

    drift_warning_count = sum(len(row.drift_warnings or []) for row in cases)

    return {
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": precision,
        "recall": recall,
        "pass_rate": pass_rate,
        "mock_score_distribution": mock_margins,
        "drift_warning_count": drift_warning_count,
    }


def build_v1_mode_metrics(cases: Sequence[V1CaseTelemetry]) -> dict[str, Any]:
    """Pass-rate summary for V1 rule-based golden cases."""
    passed = sum(1 for row in cases if row.passed)
    return {
        "cases": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "pass_rate": _safe_ratio(passed, len(cases)),
        "breakdown": [
            {"case_id": row.case_id, "expectation": row.expectation, "passed": row.passed, "detail": row.detail}
            for row in cases
        ],
    }
