"""Backend contract validation: validate_status_contract and write guards."""

import pytest

from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import validate_status_contract


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
