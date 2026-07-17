# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for PipelineRepository UPSERT and warning semantics."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import FailedDuringStage, PaperStatus, PaperStatusData, PipelineStage


@pytest.mark.asyncio
async def test_save_status_inserts_then_upserts_single_row(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("pipe-001", "Pipe", "/tmp/pipe.pdf")

    now = datetime.now(UTC)
    pending = PaperStatusData(
        paper_id="pipe-001",
        status=PaperStatus.PENDING,
        percent=0,
        stage=None,
        message="queued",
        updated_at=now,
    )
    await pipeline_repo.save_status("pipe-001", pending)

    processing = pending.model_copy(
        update={
            "status": PaperStatus.PROCESSING,
            "stage": PipelineStage.INGESTING,
            "percent": 20,
            "message": "ingesting",
        },
    )
    await pipeline_repo.save_status("pipe-001", processing)

    latest = await pipeline_repo.get_latest("pipe-001")
    assert latest is not None
    assert latest.status == PaperStatus.PROCESSING
    assert latest.stage == PipelineStage.INGESTING
    assert latest.percent == 20


@pytest.mark.asyncio
async def test_record_warnings_appends_without_overwriting(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("warn-001", "Warn", "/tmp/warn.pdf")
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "warn-001",
        PaperStatusData(
            paper_id="warn-001",
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="classifying",
            updated_at=now,
            classify_warnings=["classifier_heuristic_fallback"],
        ),
    )

    await pipeline_repo.record_warnings(
        "warn-001",
        classify=["extract_heuristic_fallback"],
        extract=["low_confidence_graph"],
    )

    latest = await pipeline_repo.get_latest("warn-001")
    assert latest is not None
    assert latest.classify_warnings == [
        "classifier_heuristic_fallback",
        "extract_heuristic_fallback",
    ]
    assert latest.extract_warnings == ["low_confidence_graph"]


@pytest.mark.asyncio
async def test_failed_status_persists_error_fields(persistence_env) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create("fail-001", "Fail", "/tmp/fail.pdf")
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "fail-001",
        PaperStatusData(
            paper_id="fail-001",
            status=PaperStatus.FAILED,
            percent=0,
            stage=PipelineStage.FAILED,
            message="boom",
            updated_at=now,
            error_code="PIPELINE_FAILED",
            failed_during=FailedDuringStage.EXTRACTING,
        ),
    )

    latest = await pipeline_repo.get_latest("fail-001")
    assert latest is not None
    assert latest.error_code == "PIPELINE_FAILED"
    assert latest.failed_during == FailedDuringStage.EXTRACTING
