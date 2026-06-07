"""Facade smoke tests for PipelineStatusService (see test_status_contract / test_pipeline_status_updates)."""

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import (
    PipelineStatusService,
    validate_status_contract,
)
from tests.helpers.status_contract import assert_snapshot_matches_contract


@pytest.mark.parametrize(
    ("status", "stage", "percent"),
    [
        (PaperStatus.PENDING, None, 0),
        (PaperStatus.PROCESSING, PipelineStage.INGESTING, 20),
        (PaperStatus.PROCESSING, PipelineStage.HEAD_REFINING, 35),
        (PaperStatus.PROCESSING, PipelineStage.CLASSIFYING, 50),
        (PaperStatus.PROCESSING, PipelineStage.EXTRACTING, 80),
        (PaperStatus.PROCESSING, PipelineStage.STORING, 95),
        (PaperStatus.READY, PipelineStage.READY, 100),
        (PaperStatus.FAILED, PipelineStage.FAILED, 0),
    ],
)
def test_validate_status_contract_accepts_api_pairs(
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
) -> None:
    validate_status_contract(status=status, stage=stage, percent=percent)


@pytest.mark.parametrize(
    ("status", "stage", "percent"),
    [
        (PaperStatus.PENDING, PipelineStage.INGESTING, 0),
        (PaperStatus.PROCESSING, PipelineStage.READY, 50),
        (PaperStatus.READY, PipelineStage.STORING, 100),
        (PaperStatus.FAILED, PipelineStage.INGESTING, 0),
    ],
)
def test_validate_status_contract_rejects_invalid_triples(
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
) -> None:
    with pytest.raises(ValueError):
        validate_status_contract(status=status, stage=stage, percent=percent)


def test_start_processing_sets_ingesting_percent(registered_paper: str) -> None:
    svc = PipelineStatusService()
    snapshot = svc.start_processing(registered_paper)
    assert snapshot.status == PaperStatus.PROCESSING
    assert snapshot.stage == PipelineStage.INGESTING
    assert snapshot.percent == STAGE_PERCENT[PipelineStage.INGESTING]
    assert_snapshot_matches_contract(snapshot)


def test_advance_head_refining_stage_visible_in_status(registered_paper: str) -> None:
    svc = PipelineStatusService()
    svc.start_processing(registered_paper)
    snapshot = svc.advance_stage(registered_paper, PipelineStage.HEAD_REFINING)

    assert snapshot.stage == PipelineStage.HEAD_REFINING
    assert snapshot.percent == STAGE_PERCENT[PipelineStage.HEAD_REFINING]
    assert "精炼" in snapshot.message
    assert_snapshot_matches_contract(snapshot)


def test_advance_stage_updates_snapshot(registered_paper: str) -> None:
    svc = PipelineStatusService()
    svc.start_processing(registered_paper)
    snapshot = svc.advance_stage(registered_paper, PipelineStage.EXTRACTING)
    assert snapshot.stage == PipelineStage.EXTRACTING
    assert snapshot.percent == 80


async def test_mark_ready_visible_via_get_status(registered_paper: str) -> None:
    PipelineStatusService().mark_ready(registered_paper)
    status = await get_paper_service().get_status(registered_paper)
    assert status.status == PaperStatus.READY
    assert status.stage == PipelineStage.READY
    assert status.percent == 100


async def test_mark_failed_visible_via_get_status(registered_paper: str) -> None:
    PipelineStatusService().mark_failed(
        registered_paper,
        message="测试失败",
        error_code="INGEST_FAILED",
        failed_during=PipelineStage.CLASSIFYING,
    )
    status = await get_paper_service().get_status(registered_paper)
    assert status.status == PaperStatus.FAILED
    assert status.stage == PipelineStage.FAILED
    assert status.percent == 0
