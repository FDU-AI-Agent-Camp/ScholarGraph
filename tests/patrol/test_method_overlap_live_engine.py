# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for method_overlap live assertion engine (no network)."""

from __future__ import annotations

import pytest
from backend.config import get_settings
from backend.schemas.patrol import (
    MethodOverlapPoint,
    OverlapType,
    PatrolInsight,
    PatrolInsightStatus,
)
from tests.fixtures.patrol_method_overlap_golden import (
    DriftGuardSpec,
    GoldenArchetype,
    GoldenExpectationBlock,
    GoldenExpectedStatus,
    load_method_overlap_golden_set,
)
from tests.patrol.conftest import patch_patrol_settings
from tests.patrol.method_overlap_live_engine import assert_drift_guard, assert_primary_expectation


def _ready_insight(*, match_type: str, overlap_label: str, score: float) -> PatrolInsight:
    return PatrolInsight(
        insight_id="ins-test",
        title="t",
        summary="s",
        status=PatrolInsightStatus.READY,
        paper_ids=["a", "b"],
        structured_points=[
            MethodOverlapPoint(
                mode="method_overlap",
                overlap_type=OverlapType.METHOD,
                overlap_label=overlap_label,
                paper_a_usage="ua",
                paper_b_usage="ub",
                match_type=match_type,  # type: ignore[arg-type]
                overlap_score=score,
            ),
        ],
    )


def test_drift_guard_fails_when_cosine_meets_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_patrol_settings(monkeypatch, patrol_semantic_threshold=0.88)
    pair = next(
        p for p in load_method_overlap_golden_set().pairs if p.archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE
    )
    settings = get_settings()

    passed, detail = assert_drift_guard(0.91, pair, settings=settings)
    assert passed is False
    assert "NB_LR_FALSE_POSITIVE" in detail
    assert "drift guard" in detail.lower() or "drift" in detail.lower()


def test_drift_guard_passes_when_cosine_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_patrol_settings(monkeypatch, patrol_semantic_threshold=0.88)
    pair = next(
        p for p in load_method_overlap_golden_set().pairs if p.archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE
    )
    settings = get_settings()

    passed, detail = assert_drift_guard(0.55, pair, settings=settings)
    assert passed is True
    assert "0.55" in detail


def test_primary_expectation_checks_overlap_label() -> None:
    pair = next(
        p for p in load_method_overlap_golden_set().pairs if p.archetype == GoldenArchetype.LITERAL_TRUE_POSITIVE
    )
    insight = _ready_insight(match_type="literal", overlap_label="BERT", score=1.0)
    passed, _ = assert_primary_expectation(insight, pair)
    assert passed is True

    wrong_label = _ready_insight(match_type="literal", overlap_label="WRONG", score=1.0)
    passed, detail = assert_primary_expectation(wrong_label, pair)
    assert passed is False
    assert "overlap_label" in detail


def test_drift_guard_warn_only_when_strict_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATROL_LIVE_DRIFT_GUARD_STRICT", "0")
    patch_patrol_settings(monkeypatch, patrol_semantic_threshold=0.88)
    pair = next(
        p for p in load_method_overlap_golden_set().pairs if p.archetype == GoldenArchetype.CORRELATED_FALSE_POSITIVE
    )
    pair = pair.model_copy(
        update={
            "expectation": GoldenExpectationBlock(
                expected_status=GoldenExpectedStatus.INSUFFICIENT_DATA,
                drift_guard=DriftGuardSpec(enabled=True, require_below_semantic_threshold=True),
            ),
        },
    )
    settings = get_settings()
    passed, detail = assert_drift_guard(0.95, pair, settings=settings)
    assert passed is True
    assert "WARN" in detail
