"""Backend contract validation: validate_status_contract and write guards."""

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import (
    validate_failed_error_fields,
    validate_status_contract,
)

# ── validate_status_contract (pure) ─────────────────────────────────────────


@pytest.mark.parametrize(
    "stage",
    [PipelineStage.INGESTING, PipelineStage.CLASSIFYING, PipelineStage.EXTRACTING, PipelineStage.STORING],
)
def test_processing_stage_percent_must_match_stage_percent(stage: PipelineStage) -> None:
    validate_status_contract(
        status=PaperStatus.PROCESSING,
        stage=stage,
        percent=STAGE_PERCENT[stage],
    )


@pytest.mark.parametrize(
    ("stage", "wrong_percent"),
    [
        (PipelineStage.INGESTING, 0),
        (PipelineStage.INGESTING, 50),
        (PipelineStage.CLASSIFYING, 20),
        (PipelineStage.EXTRACTING, 95),
        (PipelineStage.STORING, 80),
    ],
)
def test_processing_rejects_percent_mismatch(stage: PipelineStage, wrong_percent: int) -> None:
    with pytest.raises(ValueError, match="percent"):
        validate_status_contract(
            status=PaperStatus.PROCESSING,
            stage=stage,
            percent=wrong_percent,
        )


def test_pending_rejects_non_null_stage() -> None:
    with pytest.raises(ValueError, match="stage"):
        validate_status_contract(
            status=PaperStatus.PENDING,
            stage=PipelineStage.INGESTING,
            percent=0,
        )


@pytest.mark.parametrize("percent", [1, 20, 100])
def test_pending_rejects_nonzero_percent(percent: int) -> None:
    with pytest.raises(ValueError, match="percent"):
        validate_status_contract(status=PaperStatus.PENDING, stage=None, percent=percent)


def test_processing_rejects_ready_stage() -> None:
    with pytest.raises(ValueError, match="stage"):
        validate_status_contract(
            status=PaperStatus.PROCESSING,
            stage=PipelineStage.READY,
            percent=50,
        )


def test_processing_rejects_failed_stage() -> None:
    with pytest.raises(ValueError, match="stage"):
        validate_status_contract(
            status=PaperStatus.PROCESSING,
            stage=PipelineStage.FAILED,
            percent=0,
        )


def test_processing_rejects_null_stage() -> None:
    with pytest.raises(ValueError, match="stage"):
        validate_status_contract(status=PaperStatus.PROCESSING, stage=None, percent=20)


def test_ready_rejects_wrong_stage() -> None:
    with pytest.raises(ValueError, match="ready"):
        validate_status_contract(
            status=PaperStatus.READY,
            stage=PipelineStage.STORING,
            percent=100,
        )


def test_ready_rejects_percent_below_100() -> None:
    with pytest.raises(ValueError, match="ready"):
        validate_status_contract(
            status=PaperStatus.READY,
            stage=PipelineStage.READY,
            percent=95,
        )


def test_failed_rejects_nonzero_percent() -> None:
    with pytest.raises(ValueError, match="failed"):
        validate_status_contract(
            status=PaperStatus.FAILED,
            stage=PipelineStage.FAILED,
            percent=20,
        )


def test_failed_rejects_wrong_stage() -> None:
    with pytest.raises(ValueError, match="failed"):
        validate_status_contract(
            status=PaperStatus.FAILED,
            stage=PipelineStage.CLASSIFYING,
            percent=0,
        )


# ── PaperService write guard ────────────────────────────────────────────────


def test_update_pipeline_status_rejects_invalid_contract(registered_paper: str) -> None:
    with pytest.raises(ValueError):
        get_paper_service().update_pipeline_status(
            registered_paper,
            status=PaperStatus.PROCESSING,
            stage=PipelineStage.CLASSIFYING,
            percent=20,
            message="percent 与 stage 不一致",
        )


def test_set_status_snapshot_rejects_invalid_contract(registered_paper: str) -> None:
    with pytest.raises(ValueError):
        get_paper_service().set_status_snapshot(
            registered_paper,
            status=PaperStatus.READY,
            stage=PipelineStage.READY,
            percent=50,
            message="非法 ready 快照",
        )


def test_failed_requires_error_code() -> None:
    with pytest.raises(ValueError, match="error_code"):
        validate_failed_error_fields(
            status=PaperStatus.FAILED,
            error_code=None,
            failed_during=None,
        )


def test_failed_rejects_invalid_failed_during() -> None:
    with pytest.raises(ValueError, match="failed_during"):
        validate_failed_error_fields(
            status=PaperStatus.FAILED,
            error_code="PIPELINE_FAILED",
            failed_during=PipelineStage.FAILED,
        )


def test_non_failed_rejects_error_fields() -> None:
    with pytest.raises(ValueError, match="非 failed"):
        validate_failed_error_fields(
            status=PaperStatus.READY,
            error_code="PIPELINE_FAILED",
            failed_during=None,
        )


def test_mark_failed_persists_error_code_and_failed_during(registered_paper: str) -> None:
    from backend.services.pipeline_status_service import PipelineStatusService

    snapshot = PipelineStatusService().mark_failed(
        registered_paper,
        message="范式分类失败",
        error_code="LLM_JSON_INVALID",
        failed_during=PipelineStage.CLASSIFYING,
    )
    assert snapshot.error_code == "LLM_JSON_INVALID"
    assert snapshot.failed_during == PipelineStage.CLASSIFYING
    validate_failed_error_fields(
        status=snapshot.status,
        error_code=snapshot.error_code,
        failed_during=snapshot.failed_during,
    )


def test_update_pipeline_status_accepts_valid_processing_triple(registered_paper: str) -> None:
    snapshot = get_paper_service().update_pipeline_status(
        registered_paper,
        status=PaperStatus.PROCESSING,
        stage=PipelineStage.STORING,
        percent=STAGE_PERCENT[PipelineStage.STORING],
        message="写入存储",
    )
    assert snapshot.stage == PipelineStage.STORING
    assert snapshot.percent == 95
