"""PaperStatusData schema and fixture contract tests."""

import json
from datetime import UTC, datetime
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


def test_paper_status_data_defaults_head_refine_warnings_to_empty_list() -> None:
    status = PaperStatusData(
        paper_id="schema-default",
        status=PaperStatus.PROCESSING,
        percent=35,
        stage=PipelineStage.HEAD_REFINING,
        message="正在精炼文档头部…",
        updated_at=datetime.now(UTC),
    )
    assert status.head_refine_warnings == []


def test_paper_status_data_defaults_extract_warnings_to_empty_list() -> None:
    status = PaperStatusData(
        paper_id="schema-default",
        status=PaperStatus.PROCESSING,
        percent=80,
        stage=PipelineStage.EXTRACTING,
        message="正在抽取逻辑图谱",
        updated_at=datetime.now(UTC),
    )
    assert status.extract_warnings == []


def test_head_refining_stage_validates_with_contract_percent() -> None:
    from backend.services.pipeline_status_service import validate_status_contract

    validate_status_contract(
        status=PaperStatus.PROCESSING,
        stage=PipelineStage.HEAD_REFINING,
        percent=35,
    )


def test_hss_002_per_paper_status_fixture() -> None:
    status = _load_status_data("paper-status-hss-002.json")
    assert status.paper_id == "hss-002"
    assert status.status == PaperStatus.PROCESSING
    assert status.stage == PipelineStage.CLASSIFYING


def test_ready_fallback_status_fixture_includes_extract_warnings() -> None:
    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE

    status = _load_status_data("paper-status-ready-fallback.json")
    assert status.status == PaperStatus.READY
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]
