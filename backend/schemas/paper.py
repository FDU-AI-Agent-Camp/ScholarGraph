"""Paper lifecycle and summary schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.schemas.paradigm import Paradigm, ParadigmClassification


class PaperStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class PipelineStage(StrEnum):
    INGESTING = "ingesting"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    STORING = "storing"
    READY = "ready"
    FAILED = "failed"


class FailedDuringStage(StrEnum):
    INGESTING = "ingesting"
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
    error_code: str | None = Field(
        default=None,
        description="Machine-readable code when status=failed.",
    )
    failed_during: FailedDuringStage | None = Field(
        default=None,
        description="Pipeline step that was running when failure occurred (ingesting–storing only).",
    )
