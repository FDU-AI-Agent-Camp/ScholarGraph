"""Integration tests: full pipeline status progression persisted to DB (INT-PIPE-01/02)."""

from __future__ import annotations

import asyncio

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.pipeline_status_service import PROCESSING_STAGES, PipelineStatusService
from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_stage_progression_persists_each_step(persistence_env) -> None:
    paper_id = "pipe-full-001"
    await register_test_paper(paper_id)
    service = await restart_paper_service()
    pss = PipelineStatusService()

    pss.start_processing(paper_id)
    status = await service.get_status(paper_id)
    assert status.stage == PipelineStage.INGESTING
    assert status.percent == STAGE_PERCENT[PipelineStage.INGESTING]

    for stage in (
        PipelineStage.HEAD_REFINING,
        PipelineStage.CLASSIFYING,
        PipelineStage.EXTRACTING,
        PipelineStage.STORING,
    ):
        pss.advance_stage(paper_id, stage)
        status = await service.get_status(paper_id)
        assert status.stage == stage
        assert status.percent == STAGE_PERCENT[stage]
        assert status.status == PaperStatus.PROCESSING

    pss.mark_ready(paper_id)
    status = await service.get_status(paper_id)
    assert status.stage == PipelineStage.READY
    assert status.percent == 100
    assert status.status == PaperStatus.READY


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_failed_persists_error_fields_across_restart(persistence_env) -> None:
    paper_id = "pipe-fail-001"
    await register_test_paper(paper_id)
    service = await restart_paper_service()
    PipelineStatusService().advance_stage(paper_id, PipelineStage.EXTRACTING)
    PipelineStatusService().mark_failed(
        paper_id,
        message="抽取失败",
        error_code="EXTRACT_FAILED",
        failed_during=PipelineStage.EXTRACTING,
    )

    service = await restart_paper_service()
    status = await service.get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.stage == PipelineStage.FAILED
    assert status.percent == 0
    assert status.error_code == "EXTRACT_FAILED"
    assert status.failed_during is not None
    assert status.failed_during.value == PipelineStage.EXTRACTING.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_stage_upserts_do_not_raise_database_locked(persistence_env) -> None:
    """Stress: parallel status UPSERT should not raise database is locked (P1.5)."""
    from backend.repositories.paper_repository import PaperRepository
    from backend.schemas.paper import PaperStatusData
    from datetime import UTC, datetime

    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    paper_id = "stress-001"
    await paper_repo.create(paper_id, "Stress", "/tmp/s.pdf")
    now = datetime.now(UTC)

    async def write_once(stage: PipelineStage, percent: int) -> None:
        await pipeline_repo.save_status(
            paper_id,
            PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.PROCESSING,
                percent=percent,
                stage=stage,
                message=stage.value,
                updated_at=now,
            ),
        )

    await asyncio.gather(
        write_once(PipelineStage.INGESTING, 20),
        write_once(PipelineStage.CLASSIFYING, 50),
        write_once(PipelineStage.EXTRACTING, 80),
    )

    latest = await pipeline_repo.get_latest(paper_id)
    assert latest is not None
    assert latest.stage in PROCESSING_STAGES
