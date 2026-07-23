# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for dual-table status drift audit and heal."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import FailedDuringStage, PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
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
    pipeline_repo = get_pipeline_repository()

    await pipeline_repo.save_status(
        paper_id,
        _snapshot(
            paper_id,
            status=PaperStatus.INDEXING,
            stage=PipelineStage.EXTRACTING,
            percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
            message="stale pipeline row",
        ),
    )
    drifted = await pipeline_repo.get_latest(paper_id)
    assert drifted is not None
    healed = await ensure_status_contract(service, paper_id, drifted)

    assert healed.status == PaperStatus.INDEXING
    assert healed.stage == PipelineStage.INDEXING
    assert healed.percent == STAGE_PERCENT[PipelineStage.INDEXING]

    reloaded = await service.get_status(paper_id)
    assert reloaded.stage == PipelineStage.INDEXING
    assert reloaded.percent == STAGE_PERCENT[PipelineStage.INDEXING]


@pytest.mark.asyncio
async def test_ensure_status_contract_indexing_heal_does_not_clobber_ready_promote(
    persistence_env,
) -> None:
    """Stale INDEXING heal must not overwrite a concurrent READY promote (HTTP poll race)."""
    paper_id = "guard-indexing-vs-ready"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = await restart_paper_service()
    pipeline_ops = get_paper_pipeline_ops_service()

    await persist_status_snapshot(
        service,
        paper_id,
        status=PaperStatus.INDEXING,
        stage=PipelineStage.INDEXING,
        percent=STAGE_PERCENT[PipelineStage.INDEXING],
        message="indexing",
    )

    # Stale dual-table assemble: status=INDEXING but stage/percent still extracting.
    stale = _snapshot(
        paper_id,
        status=PaperStatus.INDEXING,
        stage=PipelineStage.EXTRACTING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        message="stale",
    )

    async def _promote() -> PaperStatusData:
        return await pipeline_ops.promote_paper_to_terminal_status(
            paper_id,
            success=True,
            preferred_terminal=PaperStatus.READY,
            publish_rag_indexed=False,
        )

    async def _heal_stale() -> PaperStatusData:
        return await ensure_status_contract(service, paper_id, stale)

    await asyncio.gather(_promote(), _heal_stale())

    latest = await pipeline_ops.get_pipeline_snapshot(paper_id)
    assert latest is not None
    assert latest.status == PaperStatus.READY
    assert latest.stage == PipelineStage.READY
    assert latest.percent == 100


@pytest.mark.asyncio
async def test_ensure_status_contract_indexing_heal_rereads_ready_after_promote(
    persistence_env,
) -> None:
    """When repair returns None because promote already won, re-read must yield READY."""
    paper_id = "guard-indexing-reread-ready"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = await restart_paper_service()
    pipeline_ops = get_paper_pipeline_ops_service()

    await persist_status_snapshot(
        service,
        paper_id,
        status=PaperStatus.INDEXING,
        stage=PipelineStage.INDEXING,
        percent=STAGE_PERCENT[PipelineStage.INDEXING],
        message="indexing",
    )
    await pipeline_ops.promote_paper_to_terminal_status(
        paper_id,
        success=True,
        preferred_terminal=PaperStatus.READY,
        publish_rag_indexed=False,
    )

    stale = _snapshot(
        paper_id,
        status=PaperStatus.INDEXING,
        stage=PipelineStage.EXTRACTING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        message="stale after promote",
    )
    healed = await ensure_status_contract(service, paper_id, stale)
    assert healed.status == PaperStatus.READY
    assert healed.stage == PipelineStage.READY
    assert healed.percent == 100


@pytest.mark.asyncio
async def test_ensure_status_contract_heals_failed_drift(persistence_env) -> None:
    paper_id = "guard-failed-drift"
    await register_test_paper(paper_id, status=PaperStatus.FAILED)
    service = await restart_paper_service()
    pipeline_repo = get_pipeline_repository()

    await pipeline_repo.save_status(
        paper_id,
        _snapshot(
            paper_id,
            status=PaperStatus.FAILED,
            stage=PipelineStage.EXTRACTING,
            percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
            message="extract blew up",
            error_code="EXTRACT_FAILED",
            failed_during=FailedDuringStage.EXTRACTING,
        ),
    )

    drifted = await pipeline_repo.get_latest(paper_id)
    assert drifted is not None
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
    pipeline_repo = get_pipeline_repository()

    await pipeline_repo.save_status(
        paper_id,
        _snapshot(
            paper_id,
            status=PaperStatus.READY_WITH_WARNINGS,
            stage=PipelineStage.STORING,
            percent=STAGE_PERCENT[PipelineStage.STORING],
        ),
    )
    drifted = await pipeline_repo.get_latest(paper_id)
    assert drifted is not None
    healed = await ensure_status_contract(service, paper_id, drifted)

    assert healed.status == PaperStatus.READY_WITH_WARNINGS
    assert healed.stage == PipelineStage.READY
    assert healed.percent == STAGE_PERCENT[PipelineStage.READY]


@pytest.mark.asyncio
async def test_persist_status_snapshot_heals_dual_table_drift_and_logs_audit(
    persistence_env,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Dual-table drift → persist_status_snapshot recovers DB and audits heal."""
    import logging

    paper_id = "guard-persist-heal-audit"
    await register_test_paper(paper_id, status=PaperStatus.READY)
    service = await restart_paper_service()
    pipeline_repo = get_pipeline_repository()
    pipeline_ops = get_paper_pipeline_ops_service()

    await pipeline_repo.save_status(
        paper_id,
        _snapshot(
            paper_id,
            status=PaperStatus.READY,
            stage=PipelineStage.EXTRACTING,
            percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
            message="dual-table drift",
        ),
    )
    drifted = await pipeline_ops.get_pipeline_snapshot(paper_id)
    assert drifted is not None
    assert drifted.stage == PipelineStage.EXTRACTING

    with caplog.at_level(logging.WARNING, logger="backend.services.paper_pipeline_ops"):
        healed = await persist_status_snapshot(
            service,
            paper_id,
            status=PaperStatus.READY,
            stage=PipelineStage.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            message="建图完成",
        )

    assert healed.status == PaperStatus.READY
    assert healed.stage == PipelineStage.READY
    assert healed.percent == STAGE_PERCENT[PipelineStage.READY]

    reloaded = await pipeline_ops.get_pipeline_snapshot(paper_id)
    assert reloaded is not None
    assert reloaded.status == PaperStatus.READY
    assert reloaded.stage == PipelineStage.READY
    assert reloaded.percent == STAGE_PERCENT[PipelineStage.READY]
    assert reloaded.message == "建图完成"

    audit_records = [
        record
        for record in caplog.records
        if record.getMessage() == "pipeline_snapshot_heal_applied"
    ]
    assert len(audit_records) == 1
    audit = audit_records[0]
    assert audit.levelno == logging.WARNING
    assert getattr(audit, "paper_id", None) == paper_id
    assert getattr(audit, "heal_reason", None) == "contract_drift_heal"
    assert getattr(audit, "target_status", None) == PaperStatus.READY.value


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
