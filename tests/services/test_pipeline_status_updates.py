# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests: pipeline status progression via PipelineStatusService."""

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import PipelineStatusService
from tests.helpers.status_contract import assert_snapshot_matches_contract

PROCESSING_SEQUENCE: tuple[PipelineStage, ...] = (
    PipelineStage.INGESTING,
    PipelineStage.HEAD_REFINING,
    PipelineStage.CLASSIFYING,
    PipelineStage.EXTRACTING,
    PipelineStage.STORING,
)


@pytest.mark.asyncio
async def test_full_processing_sequence_matches_contract_percents(registered_paper: str) -> None:
    svc = PipelineStatusService()
    await svc.start_processing(registered_paper)
    for stage in PROCESSING_SEQUENCE[1:]:
        snapshot = await svc.advance_stage(registered_paper, stage)
        assert snapshot.stage == stage
        assert snapshot.percent == STAGE_PERCENT[stage]
        assert_snapshot_matches_contract(snapshot)


@pytest.mark.asyncio
async def test_start_processing_syncs_paper_detail_status(registered_paper: str) -> None:
    await PipelineStatusService().start_processing(registered_paper)
    paper = await get_paper_service().get_paper(registered_paper)
    assert paper.status == PaperStatus.PROCESSING


async def test_get_status_reflects_each_advance(registered_paper: str) -> None:
    svc = PipelineStatusService()
    await svc.start_processing(registered_paper)
    status = await get_paper_service().get_status(registered_paper)
    assert status.stage == PipelineStage.INGESTING
    assert status.percent == 20

    await svc.advance_stage(registered_paper, PipelineStage.CLASSIFYING)
    status = await get_paper_service().get_status(registered_paper)
    assert status.stage == PipelineStage.CLASSIFYING
    assert status.percent == 50
    assert_snapshot_matches_contract(status)


@pytest.mark.parametrize(
    "terminal_stage",
    [PipelineStage.READY, PipelineStage.FAILED],
)
@pytest.mark.asyncio
async def test_advance_stage_rejects_terminal_stages(
    registered_paper: str,
    terminal_stage: PipelineStage,
) -> None:
    await PipelineStatusService().start_processing(registered_paper)
    with pytest.raises(ValueError, match="终态"):
        await PipelineStatusService().advance_stage(registered_paper, terminal_stage)


async def test_mark_ready_and_failed_snapshots_match_contract(registered_paper: str) -> None:
    svc = PipelineStatusService()
    ready = await svc.mark_ready(registered_paper)
    assert_snapshot_matches_contract(ready)

    await svc.mark_failed(registered_paper, message="重试失败", error_code="PIPELINE_FAILED")
    failed = await get_paper_service().get_status(registered_paper)
    assert_snapshot_matches_contract(failed)


async def test_get_status_pending_without_snapshot_uses_contract_defaults(
    registered_paper: str,
) -> None:
    status = await get_paper_service().get_status(registered_paper)
    assert status.status == PaperStatus.PENDING
    assert status.stage is None
    assert status.percent == 0
    assert_snapshot_matches_contract(status)
