# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for dual-table status drift audit and heal."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import FailedDuringStage, PaperStatus, PaperStatusData, PipelineStage
from backend.services.status_snapshot_guard import (
    audit_dual_table_invariant,
    ensure_status_contract,
    persist_status_snapshot,
)
from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service


def _snapshot(
    paper_id: str,
    *,
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
    message: str = "drifted",
    error_code: str | None = None,
    failed_during: FailedDuringStage | None = None,
    extract_warnings: list[str] | None = None,
) -> PaperStatusData:
    now = datetime.now(UTC)
    return PaperStatusData(
        paper_id=paper_id,
        status=status,
        percent=percent,
        stage=stage,
        message=message,
        updated_at=now,
        error_code=error_code,
        failed_during=failed_during,
        extract_warnings=extract_warnings or [],
    )


def test_audit_dual_table_invariant_logs_ready_stage_mismatch(caplog: pytest.LogCaptureFixture) -> None:
    snapshot = _snapshot(
        "audit-ready",
        status=PaperStatus.READY,
        stage=PipelineStage.EXTRACTING,
        percent=80,
    )
    with caplog.at_level("CRITICAL"):
        audit_dual_table_invariant(snapshot)
    assert any("pipeline_dual_table_invariant_violation" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_ensure_status_contract_heals_indexing_drift(persistence_env) -> None:
    paper_id = "guard-indexing-drift"
    await register_test_paper(paper_id, status=PaperStatus.INDEXING)
    service = await restart_paper_service()

    drifted = _snapshot(
        paper_id,
        status=PaperStatus.INDEXING,
        stage=PipelineStage.EXTRACTING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        message="stale pipeline row",
    )
    healed = await ensure_status_contract(service, paper_id, drifted)

    assert healed.status == PaperStatus.INDEXING
    assert healed.stage == PipelineStage.INDEXING
    assert healed.percent == STAGE_PERCENT[PipelineStage.INDEXING]

    reloaded = await service.get_status(paper_id)
    assert reloaded.stage == PipelineStage.INDEXING
    assert reloaded.percent == STAGE_PERCENT[PipelineStage.INDEXING]


@pytest.mark.asyncio
async def test_ensure_status_contract_heals_failed_drift(persistence_env) -> None:
    paper_id = "guard-failed-drift"
    await register_test_paper(paper_id, status=PaperStatus.FAILED)
    service = await restart_paper_service()

    drifted = _snapshot(
        paper_id,
        status=PaperStatus.FAILED,
        stage=PipelineStage.EXTRACTING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        message="extract blew up",
        error_code="EXTRACT_FAILED",
        failed_during=FailedDuringStage.EXTRACTING,
    )
    healed = await ensure_status_contract(service, paper_id, drifted)

    assert healed.status == PaperStatus.FAILED
    assert healed.stage == PipelineStage.FAILED
    assert healed.percent == 0
    assert healed.error_code == "EXTRACT_FAILED"
    assert healed.failed_during == FailedDuringStage.EXTRACTING


@pytest.mark.asyncio
async def test_ensure_status_contract_heals_ready_with_warnings_drift(persistence_env) -> None:
    paper_id = "guard-rww-drift"
    await register_test_paper(paper_id, status=PaperStatus.READY_WITH_WARNINGS)
    service = await restart_paper_service()

    drifted = _snapshot(
        paper_id,
        status=PaperStatus.READY_WITH_WARNINGS,
        stage=PipelineStage.STORING,
        percent=STAGE_PERCENT[PipelineStage.STORING],
    )
    healed = await ensure_status_contract(service, paper_id, drifted)

    assert healed.status == PaperStatus.READY_WITH_WARNINGS
    assert healed.stage == PipelineStage.READY
    assert healed.percent == STAGE_PERCENT[PipelineStage.READY]


@pytest.mark.asyncio
async def test_persist_status_snapshot_merges_extract_warnings_without_overwrite(persistence_env) -> None:
    paper_id = "guard-warning-merge"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = await restart_paper_service()
    pipeline_repo = get_pipeline_repository()

    await pipeline_repo.save_status(
        paper_id,
        _snapshot(
            paper_id,
            status=PaperStatus.PROCESSING,
            stage=PipelineStage.EXTRACTING,
            percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
            extract_warnings=["rag_index_failed"],
        ),
    )

    saved = await persist_status_snapshot(
        service,
        paper_id,
        status=PaperStatus.PROCESSING,
        stage=PipelineStage.EXTRACTING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        message="still extracting",
        append_extract_warnings=["extract_heuristic_fallback", "rag_index_failed"],
    )

    assert saved.extract_warnings == ["rag_index_failed", "extract_heuristic_fallback"]
