"""Patrol schema alignment with OpenAPI fixtures."""

import json
from pathlib import Path

import pytest
from backend.schemas.patrol import (
    ClaimEvolutionPoint,
    LensClashPoint,
    MethodOverlapPoint,
    PatrolMode,
    PatrolReport,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"

_PATROL_FIXTURES = (
    ("patrol-lens-clash.json", PatrolMode.LENS_CLASH, LensClashPoint),
    ("patrol-method-overlap.json", PatrolMode.METHOD_OVERLAP, MethodOverlapPoint),
    ("patrol-claim-evolution.json", PatrolMode.CLAIM_EVOLUTION, ClaimEvolutionPoint),
)


@pytest.mark.parametrize(
    ("filename", "expected_mode", "point_type"),
    _PATROL_FIXTURES,
    ids=[item[0] for item in _PATROL_FIXTURES],
)
def test_patrol_fixture_round_trip(filename: str, expected_mode: PatrolMode, point_type: type) -> None:
    payload = json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))
    data = payload["data"]
    report = PatrolReport.model_validate(
        {
            **data,
            "generated_at": data.get("generated_at", "2026-07-14T00:00:00Z"),
        }
    )
    assert report.mode == expected_mode
    assert len(report.paper_ids) == 2
    assert len(report.insights) == 1
    insight = report.insights[0]
    assert len(insight.structured_points) >= 1
    assert isinstance(insight.structured_points[0], point_type)


def test_patrol_lens_clash_fixture_demo_narrative() -> None:
    payload = json.loads((FIXTURES_DIR / "patrol-lens-clash.json").read_text(encoding="utf-8"))
    data = payload["data"]
    report = PatrolReport.model_validate({**data, "generated_at": "2026-05-19T11:00:00Z"})
    assert report.paper_ids == ["hss-001", "hss-002"]
    assert report.insights[0].insight_id == "ins-001"
    assert report.insights[0].node_refs[0].node_id == "n_lens_a"


def test_patrol_report_serializes_to_openapi_json_shape() -> None:
    from datetime import UTC, datetime

    from backend.schemas.patrol import NodeRef, PatrolInsight

    report = PatrolReport(
        mode=PatrolMode.LENS_CLASH,
        paper_ids=["hss-001", "hss-002"],
        insights=[
            PatrolInsight(
                insight_id="ins-001",
                title="理论视角冲突（Lens Clash）",
                summary="summary",
                paper_ids=["hss-001", "hss-002"],
                node_refs=[
                    NodeRef(paper_id="hss-001", node_id="n_a", label="A"),
                    NodeRef(paper_id="hss-002", node_id="n_b", label="B"),
                ],
            ),
        ],
        generated_at=datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
    )
    payload = report.model_dump(mode="json")
    assert payload["mode"] == "lens_clash"
    assert "generated_at" in payload
    insight_payload = payload["insights"][0]
    assert insight_payload["node_refs"][0]["node_id"] == "n_a"
    assert insight_payload["status"] == "ready"
    assert insight_payload["has_contradiction"] is None


def test_patrol_summary_output_json_schema_fields() -> None:
    from backend.schemas.patrol_llm import PatrolSummaryOutput

    payload = PatrolSummaryOutput(
        summary="Schema 字段校验：摘要长度需满足 OpenAPI/JSON Schema 约束用于 LLM 结构化输出。",
    ).model_dump(mode="json")
    assert "summary" in payload
    assert len(payload["summary"]) >= 20
