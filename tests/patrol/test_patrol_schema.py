"""Patrol schema alignment with OpenAPI fixtures."""

import json
from pathlib import Path

from backend.schemas.patrol import PatrolMode, PatrolReport

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


def test_patrol_fixture_round_trip_except_generated_at() -> None:
    payload = json.loads((FIXTURES_DIR / "patrol-lens-clash.json").read_text(encoding="utf-8"))
    data = payload["data"]
    report = PatrolReport.model_validate(
        {
            **data,
            "generated_at": "2026-05-19T11:00:00Z",
        }
    )
    assert report.mode == PatrolMode.LENS_CLASH
    assert report.paper_ids == ["hss-001", "hss-002"]
    assert len(report.insights) == 1
    insight = report.insights[0]
    assert insight.insight_id == "ins-001"
    assert len(insight.node_refs) == 2
    assert insight.node_refs[0].paper_id == "hss-001"


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
    assert payload["insights"][0]["node_refs"][0]["node_id"] == "n_a"


def test_patrol_summary_output_json_schema_fields() -> None:
    from backend.schemas.patrol_llm import PatrolSummaryOutput

    payload = PatrolSummaryOutput(
        summary="Schema 字段校验：摘要长度需满足 OpenAPI/JSON Schema 约束用于 LLM 结构化输出。",
    ).model_dump(mode="json")
    assert "summary" in payload
    assert len(payload["summary"]) >= 20
