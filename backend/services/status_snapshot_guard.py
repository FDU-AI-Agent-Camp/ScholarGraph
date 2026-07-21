# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Repair dual-table pipeline status drift before HTTP reads."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import FailedDuringStage, PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
from backend.services.pipeline_status_service import (
    validate_failed_error_fields,
    validate_status_contract,
)

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)

TERMINAL_READY_STATUSES = frozenset({PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS})


def audit_dual_table_invariant(snapshot: PaperStatusData) -> None:
    """Log critical when ``papers.status`` and ``pipeline_runs`` diverge on HTTP reads."""
    if snapshot.status in TERMINAL_READY_STATUSES:
        if snapshot.stage != PipelineStage.READY or snapshot.percent != STAGE_PERCENT[PipelineStage.READY]:
            logger.critical(
                "pipeline_dual_table_invariant_violation",
                extra={
                    "paper_id": snapshot.paper_id,
                    "paper_status": snapshot.status.value,
                    "pipeline_stage": snapshot.stage.value if snapshot.stage is not None else None,
                    "percent": snapshot.percent,
                    "status_message": snapshot.message,
                },
            )
        return

    if snapshot.status == PaperStatus.FAILED:
        if snapshot.stage != PipelineStage.FAILED:
            logger.critical(
                "pipeline_dual_table_invariant_violation",
                extra={
                    "paper_id": snapshot.paper_id,
                    "paper_status": snapshot.status.value,
                    "pipeline_stage": snapshot.stage.value if snapshot.stage is not None else None,
                    "percent": snapshot.percent,
                    "status_message": snapshot.message,
                },
            )
        return

    if snapshot.status == PaperStatus.INDEXING:
        if snapshot.stage != PipelineStage.INDEXING or snapshot.percent != STAGE_PERCENT[PipelineStage.INDEXING]:
            logger.critical(
                "pipeline_dual_table_invariant_violation",
                extra={
                    "paper_id": snapshot.paper_id,
                    "paper_status": snapshot.status.value,
                    "pipeline_stage": snapshot.stage.value if snapshot.stage is not None else None,
                    "percent": snapshot.percent,
                    "status_message": snapshot.message,
                },
            )


def _to_failed_during(stage: PipelineStage | None) -> FailedDuringStage | None:
    if stage is None:
        return None
    return FailedDuringStage(stage.value)


async def persist_status_snapshot(
    paper_service: PaperService,
    paper_id: str,
    *,
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
    message: str,
    error_code: str | None = None,
    failed_during: PipelineStage | None = None,
    append_extract_warnings: list[str] | None = None,
) -> PaperStatusData:
    """Validate and atomically persist a pipeline status snapshot."""
    validate_status_contract(status=status, stage=stage, percent=percent)
    validate_failed_error_fields(
        status=status,
        error_code=error_code,
        failed_during=failed_during,
    )
    await paper_service.ensure_paper_exists(paper_id)
    now = datetime.now(UTC)
    preview_available = await paper_service.is_preview_available(paper_id)
    pipeline_ops = get_paper_pipeline_ops_service()
    existing = await pipeline_ops.get_pipeline_snapshot(paper_id)
    merged_extract_warnings = list(existing.extract_warnings if existing is not None else [])
    if append_extract_warnings:
        merged_extract_warnings = list(dict.fromkeys([*merged_extract_warnings, *append_extract_warnings]))
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=status,
        percent=percent,
        stage=stage,
        message=message,
        updated_at=now,
        preview_available=preview_available or bool(existing and existing.preview_available),
        error_code=error_code,
        failed_during=_to_failed_during(failed_during),
        head_refine_warnings=(existing.head_refine_warnings if existing is not None else []),
        classify_warnings=existing.classify_warnings if existing is not None else [],
        extract_warnings=merged_extract_warnings,
    )
    await pipeline_ops.save_pipeline_snapshot(paper_id, snapshot)
    return snapshot


async def ensure_status_contract(
    paper_service: PaperService,
    paper_id: str,
    snapshot: PaperStatusData,
) -> PaperStatusData:
    """Return a contract-valid snapshot, repairing known terminal/processing drift."""
    audit_dual_table_invariant(snapshot)
    try:
        validate_status_contract(
            status=snapshot.status,
            stage=snapshot.stage,
            percent=snapshot.percent,
        )
        validate_failed_error_fields(
            status=snapshot.status,
            error_code=snapshot.error_code,
            failed_during=snapshot.failed_during,
        )
        return snapshot
    except ValueError:
        if snapshot.status == PaperStatus.FAILED:
            if snapshot.stage != PipelineStage.FAILED:
                return await persist_status_snapshot(
                    paper_service,
                    paper_id,
                    status=PaperStatus.FAILED,
                    stage=PipelineStage.FAILED,
                    percent=STAGE_PERCENT[PipelineStage.FAILED],
                    message=snapshot.message or "流水线失败",
                    error_code=snapshot.error_code or "PIPELINE_FAILED",
                    failed_during=(
                        PipelineStage(snapshot.failed_during.value)
                        if snapshot.failed_during is not None
                        else PipelineStage.EXTRACTING
                    ),
                )
            return snapshot
        if snapshot.status == PaperStatus.READY:
            return await persist_status_snapshot(
                paper_service,
                paper_id,
                status=PaperStatus.READY,
                stage=PipelineStage.READY,
                percent=STAGE_PERCENT[PipelineStage.READY],
                message=snapshot.message or "建图完成",
            )
        if snapshot.status == PaperStatus.READY_WITH_WARNINGS:
            return await persist_status_snapshot(
                paper_service,
                paper_id,
                status=PaperStatus.READY_WITH_WARNINGS,
                stage=PipelineStage.READY,
                percent=STAGE_PERCENT[PipelineStage.READY],
                message=snapshot.message or "建图完成，但图谱置信度未达门控，请复核",
            )
        if snapshot.status == PaperStatus.PROCESSING and snapshot.stage is not None and snapshot.stage in STAGE_PERCENT:
            return await persist_status_snapshot(
                paper_service,
                paper_id,
                status=PaperStatus.PROCESSING,
                stage=snapshot.stage,
                percent=STAGE_PERCENT[snapshot.stage],
                message=snapshot.message,
            )
        if snapshot.status == PaperStatus.INDEXING:
            # papers.status may advance to INDEXING a tick before pipeline_runs
            # stage/percent catch up (dual-table read); repair to the P10 contract.
            return await persist_status_snapshot(
                paper_service,
                paper_id,
                status=PaperStatus.INDEXING,
                stage=PipelineStage.INDEXING,
                percent=STAGE_PERCENT[PipelineStage.INDEXING],
                message=snapshot.message or "图谱已就绪，正在构建向量索引…",
            )
        raise
