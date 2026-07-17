# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Map SQLAlchemy rows to Pydantic API schemas."""

from __future__ import annotations

from backend.db.models import PaperRow, PipelineRunRow
from backend.schemas.paper import (
    FailedDuringStage,
    PaperDetail,
    PaperStatus,
    PaperStatusData,
    PaperSummary,
    PipelineStage,
)
from backend.schemas.paradigm import Paradigm, ParadigmClassification


def _parse_paradigm(value: str | None) -> Paradigm | None:
    if value is None:
        return None
    return Paradigm(value)


def _parse_status(value: str) -> PaperStatus:
    return PaperStatus(value)


def _parse_stage(value: str | None) -> PipelineStage | None:
    if value is None:
        return None
    return PipelineStage(value)


def _parse_failed_during(value: str | None) -> FailedDuringStage | None:
    if value is None:
        return None
    return FailedDuringStage(value)


def paper_row_to_summary(row: PaperRow) -> PaperSummary:
    return PaperSummary(
        paper_id=row.paper_id,
        title=row.title or None,
        paradigm=_parse_paradigm(row.paradigm),
        status=_parse_status(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def paper_row_to_detail(row: PaperRow) -> PaperDetail:
    classification = None
    if row.classification is not None:
        classification = ParadigmClassification.model_validate(row.classification)
    return PaperDetail(
        paper_id=row.paper_id,
        title=row.title or None,
        paradigm=_parse_paradigm(row.paradigm),
        status=_parse_status(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        classification=classification,
        preview_available=bool(row.preview_available),
    )


def pipeline_row_to_status(row: PipelineRunRow) -> PaperStatusData:
    return PaperStatusData(
        paper_id=row.paper_id,
        status=_parse_status(row.paper.status),
        percent=row.percent,
        stage=_parse_stage(row.stage),
        message=row.message,
        updated_at=row.updated_at,
        preview_available=bool(row.paper.preview_available),
        error_code=row.error_code,
        failed_during=_parse_failed_during(row.failed_during),
        head_refine_warnings=list(row.head_refine_warnings or []),
        classify_warnings=list(row.classify_warnings or []),
        extract_warnings=list(row.extract_warnings or []),
    )
