"""G.2.3 unit: PaperDetail / PaperStatusData classify_warnings schema."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


def test_g23_paper_status_data_accepts_classify_warnings() -> None:
    status = PaperStatusData(
        paper_id="unit-g23-status",
        status=PaperStatus.READY,
        percent=100,
        stage=None,
        message="建图完成",
        updated_at=datetime.now(UTC),
        classify_warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    )
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_g23_paper_detail_defaults_classify_warnings_to_empty_list() -> None:
    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="unit-g23-detail",
        title="t",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    assert detail.classify_warnings == []


def test_g23_paper_detail_accepts_classify_warnings_field() -> None:
    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="unit-g23-detail-warn",
        title="t",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        classify_warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    )
    assert detail.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_g23_openapi_fixture_paper_detail_has_classify_warnings_key() -> None:
    payload = json.loads((FIXTURES_DIR / "paper-detail-ready.json").read_text(encoding="utf-8"))
    detail = PaperDetail.model_validate(payload["data"])
    assert detail.classify_warnings == []


@pytest.mark.parametrize(
    "filename",
    ("paper-detail-ready.json", "paper-detail-ready-fallback.json", "paper-detail-classify-fallback.json"),
)
def test_g20_paper_detail_fixtures_include_classify_warnings_field(filename: str) -> None:
    payload = json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))
    assert "classify_warnings" in payload["data"]
    PaperDetail.model_validate(payload["data"])


@pytest.mark.parametrize(
    "filename",
    (
        "paper-status-processing.json",
        "paper-status-ready-fallback.json",
        "paper-status-classify-fallback.json",
        "paper-status-hss-failed-001.json",
    ),
)
def test_g26_paper_status_fixtures_include_classify_warnings_field(filename: str) -> None:
    payload = json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))
    assert "classify_warnings" in payload["data"]
    PaperStatusData.model_validate(payload["data"])


def test_g26_classify_fallback_fixture_carries_machine_code() -> None:
    payload = json.loads((FIXTURES_DIR / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))
    assert payload["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
