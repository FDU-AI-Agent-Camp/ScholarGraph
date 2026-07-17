# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Schema tests for PatrolPoint discriminated union (TDD red phase)."""

import pytest
from backend.schemas.patrol import (
    ClaimEvolutionPoint,
    ContradictionPoint,
    LensClashPoint,
    MethodOverlapPoint,
    NodeRef,
    PatrolInsight,
    PatrolInsightStatus,
    PatrolMode,
    PatrolPoint,
    PatrolReport,
)
from pydantic import ValidationError


def test_all_four_point_types_serialize() -> None:
    points = [
        ContradictionPoint(mode="contradiction", point_a="A", point_b="B", conflict_type="direct"),
        LensClashPoint(mode="lens_clash", lens_a="LA", lens_b="LB", clash_aspect="ontology"),
        MethodOverlapPoint(
            mode="method_overlap",
            overlap_type="method",
            overlap_label="PCA",
            paper_a_usage="降维",
            paper_b_usage="特征选择",
            dataset_a="MNIST",
            dataset_b="CIFAR-10",
        ),
        ClaimEvolutionPoint(
            mode="claim_evolution",
            research_question="PCA 是否有效？",
            paper_a_claim="有效",
            paper_b_claim="无效",
            evidence_summary="实验结果相反",
        ),
    ]
    for point in points:
        insight = PatrolInsight(
            insight_id="ins-001",
            title="Title",
            summary="Summary",
            paper_ids=["p1", "p2"],
            structured_points=[point],
        )
        payload = insight.model_dump(mode="json")
        restored = PatrolInsight.model_validate(payload)
        assert restored.structured_points[0] == point
        if isinstance(point, MethodOverlapPoint):
            assert payload["structured_points"][0]["method"] == point.overlap_label


def test_discriminator_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        PatrolPoint.model_validate(
            {
                "mode": "unknown_mode",
                "method": "PCA",
                "paper_a_usage": "x",
                "paper_b_usage": "y",
            }
        )


def test_patrol_insight_default_structured_points() -> None:
    insight = PatrolInsight(
        insight_id="ins-001",
        title="Title",
        summary="Summary",
        paper_ids=["p1", "p2"],
        node_refs=[],
    )
    assert insight.structured_points == []


def test_patrol_report_with_structured_points_round_trip() -> None:
    from datetime import UTC, datetime

    report = PatrolReport(
        mode=PatrolMode.METHOD_OVERLAP,
        paper_ids=["stem-001", "stem-002"],
        insights=[
            PatrolInsight(
                insight_id="ins-method-overlap-001",
                title="方法重叠",
                summary="两篇论文均使用 PCA。",
                status=PatrolInsightStatus.READY,
                paper_ids=["stem-001", "stem-002"],
                node_refs=[
                    NodeRef(paper_id="stem-001", node_id="n_method", label="PCA"),
                    NodeRef(paper_id="stem-002", node_id="n_method", label="PCA"),
                ],
                structured_points=[
                    MethodOverlapPoint(
                        mode="method_overlap",
                        overlap_type="method",
                        overlap_label="PCA",
                        paper_a_usage="降维",
                        paper_b_usage="特征选择",
                    )
                ],
            )
        ],
        generated_at=datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
    )
    payload = report.model_dump(mode="json")
    restored = PatrolReport.model_validate(payload)
    assert restored == report
    assert payload["insights"][0]["structured_points"][0]["mode"] == "method_overlap"


def test_structured_points_must_match_discriminator() -> None:
    with pytest.raises(ValidationError):
        PatrolInsight(
            insight_id="ins-001",
            title="Title",
            summary="Summary",
            paper_ids=["p1", "p2"],
            structured_points=[
                {"mode": "method_overlap", "method": "PCA"}  # missing required fields
            ],
        )
