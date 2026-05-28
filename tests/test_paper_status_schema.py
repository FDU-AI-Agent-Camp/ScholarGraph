"""PaperStatusData schema and fixture contract tests."""

import json
from pathlib import Path

from backend.schemas.paper import FailedDuringStage, PaperStatus, PaperStatusData, PipelineStage

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "docs" / "api" / "fixtures"


def _load_status_data(filename: str) -> PaperStatusData:
    payload = json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))
    return PaperStatusData.model_validate(payload["data"])


def test_failed_fixture_validates_as_paper_status_data() -> None:
    status = _load_status_data("paper-status-hss-failed-001.json")
    assert status.status == PaperStatus.FAILED
    assert status.stage == PipelineStage.FAILED
    assert status.error_code == "LLM_JSON_INVALID"
    assert status.failed_during == FailedDuringStage.CLASSIFYING


def test_processing_fixture_has_no_failure_fields() -> None:
    status = _load_status_data("paper-status-processing.json")
    assert status.status == PaperStatus.PROCESSING
    assert status.error_code is None
    assert status.failed_during is None


def test_hss_002_per_paper_status_fixture() -> None:
    status = _load_status_data("paper-status-hss-002.json")
    assert status.paper_id == "hss-002"
    assert status.status == PaperStatus.PROCESSING
    assert status.stage == PipelineStage.CLASSIFYING
