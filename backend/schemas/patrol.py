"""Community patrol report schemas (BE-4) — aligned with docs/api/openapi.yaml."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PatrolMode(StrEnum):
    LENS_CLASH = "lens_clash"
    CONTRADICTION = "contradiction"


class PatrolInsightStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"


class NodeRef(BaseModel):
    paper_id: str
    node_id: str
    label: str | None = None


class PatrolInsight(BaseModel):
    insight_id: str
    title: str
    summary: str
    status: PatrolInsightStatus = Field(
        default=PatrolInsightStatus.READY,
        description=(
            "Insight readiness status. 'insufficient_data' means the graphs lack the "
            "required node types for a meaningful LLM analysis."
        ),
    )
    has_contradiction: bool | None = Field(
        default=None,
        description="Whether a contradiction was detected. Only meaningful when status='ready'.",
    )
    paper_ids: list[str] = Field(default_factory=list)
    node_refs: list[NodeRef] = Field(default_factory=list)


class PatrolReport(BaseModel):
    mode: PatrolMode
    paper_ids: list[str]
    insights: list[PatrolInsight] = Field(default_factory=list)
    generated_at: datetime
