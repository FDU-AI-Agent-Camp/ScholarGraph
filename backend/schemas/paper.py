# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper lifecycle and summary schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.schemas.ingest_head import IngestHead
from backend.schemas.paradigm import Paradigm, ParadigmClassification


class PaperStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    # Graph persisted; VectorStore index still building (P10 state gate).
    INDEXING = "indexing"
    READY = "ready"
    READY_WITH_WARNINGS = "ready_with_warnings"
    FAILED = "failed"


class PipelineStage(StrEnum):
    INGESTING = "ingesting"
    HEAD_REFINING = "head_refining"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    STORING = "storing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class FailedDuringStage(StrEnum):
    INGESTING = "ingesting"
    HEAD_REFINING = "head_refining"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    STORING = "storing"


class PaperSummary(BaseModel):
    paper_id: str
    title: str | None = None
    paradigm: Paradigm | None = None
    status: PaperStatus
    created_at: datetime
    updated_at: datetime | None = None


class PaperDetail(PaperSummary):
    classification: ParadigmClassification | None = None
    ingest_head: IngestHead | None = Field(
        default=None,
        description="Async dual(rules) merged document head with per-field sources (P10/P11).",
    )
    preview_available: bool = Field(
        default=False,
        description="True when an MVP skeleton graph is available for preview QA/graph.",
    )
    extract_warnings: list[str] = Field(
        default_factory=list,
        description="Machine-readable graph-extract degrade codes (e.g. extract_heuristic_fallback).",
    )
    classify_warnings: list[str] = Field(
        default_factory=list,
        description="Machine-readable paradigm-classifier degrade codes (e.g. classifier_heuristic_fallback).",
    )


class PaperCreateResult(BaseModel):
    paper_id: str
    status: PaperStatus
    message: str


class PaperStatusData(BaseModel):
    paper_id: str
    status: PaperStatus
    percent: int = Field(ge=0, le=100)
    stage: PipelineStage | None = None
    message: str
    updated_at: datetime
    preview_available: bool = Field(
        default=False,
        description="True when an MVP skeleton graph can be queried for preview QA/graph.",
    )
    error_code: str | None = Field(
        default=None,
        description="Machine-readable code when status=failed.",
    )
    failed_during: FailedDuringStage | None = Field(
        default=None,
        description="Pipeline step that was running when failure occurred (ingesting–storing only).",
    )
    head_refine_warnings: list[str] = Field(
        default_factory=list,
        description="Machine-readable async head-refine degrade codes (e.g. mineru_unavailable, head_refine_timeout).",
    )
    extract_warnings: list[str] = Field(
        default_factory=list,
        description="Machine-readable graph-extract degrade codes (e.g. extract_heuristic_fallback).",
    )
    classify_warnings: list[str] = Field(
        default_factory=list,
        description="Machine-readable paradigm-classifier degrade codes (e.g. classifier_heuristic_fallback).",
    )
