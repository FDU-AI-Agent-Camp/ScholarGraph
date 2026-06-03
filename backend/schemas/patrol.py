"""Community patrol report schemas (BE-4) — aligned with docs/api/openapi.yaml."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PatrolMode(StrEnum):
    LENS_CLASH = "lens_clash"
    CONTRADICTION = "contradiction"


class NodeRef(BaseModel):
    paper_id: str
    node_id: str
    label: str | None = None


class PatrolInsight(BaseModel):
    insight_id: str
    title: str
    summary: str
    paper_ids: list[str] = Field(default_factory=list)
    node_refs: list[NodeRef] = Field(default_factory=list)


class PatrolReport(BaseModel):
    mode: PatrolMode
    paper_ids: list[str]
    insights: list[PatrolInsight] = Field(default_factory=list)
    generated_at: datetime
