"""Extended PipelineRepository unit tests (test design U-PL-05~07, BND-12~13)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage


@pytest.mark.asyncio
async def test_save_status_syncs_papers_status_column(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("sync-001", "Sync", "/tmp/s.pdf", status=PaperStatus.PENDING)
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "sync-001",
        PaperStatusData(
            paper_id="sync-001",
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="classifying",
            updated_at=now,
        ),
    )
    paper = await paper_repo.get("sync-001")
    assert paper is not None
    assert paper.status == PaperStatus.PROCESSING


@pytest.mark.asyncio
async def test_record_warnings_deduplicates_codes(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("dedup-001", "Dedup", "/tmp/d.pdf")
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "dedup-001",
        PaperStatusData(
            paper_id="dedup-001",
            status=PaperStatus.PROCESSING,
            percent=80,
            stage=PipelineStage.EXTRACTING,
            message="extracting",
            updated_at=now,
            extract_warnings=["extract_heuristic_fallback"],
        ),
    )
    await pipeline_repo.record_warnings(
        "dedup-001",
        extract=["extract_heuristic_fallback", "low_confidence_graph"],
    )
    latest = await pipeline_repo.get_latest("dedup-001")
    assert latest is not None
    assert latest.extract_warnings == [
        "extract_heuristic_fallback",
        "low_confidence_graph",
    ]


@pytest.mark.asyncio
async def test_record_warnings_without_pipeline_row_raises(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("no-run", "No Run", "/tmp/n.pdf")
    with pytest.raises(KeyError, match="pipeline run not found"):
        await pipeline_repo.record_warnings("no-run", classify=["classifier_heuristic_fallback"])


@pytest.mark.asyncio
async def test_ready_snapshot_uses_percent_100_boundary(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("ready-bnd", "Ready", "/tmp/r.pdf")
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "ready-bnd",
        PaperStatusData(
            paper_id="ready-bnd",
            status=PaperStatus.READY,
            percent=100,
            stage=PipelineStage.READY,
            message="done",
            updated_at=now,
            preview_available=True,
        ),
    )
    latest = await pipeline_repo.get_latest("ready-bnd")
    assert latest is not None
    assert latest.percent == 100
    assert latest.stage == PipelineStage.READY


@pytest.mark.asyncio
async def test_record_warnings_uses_row_level_lock(persistence_env) -> None:
    """P1.5: warning append path acquires SELECT FOR UPDATE."""
    from inspect import getsource

    from backend.repositories import pipeline_repository

    source = getsource(pipeline_repository.PipelineRepository.record_warnings)
    assert "with_for_update" in source
