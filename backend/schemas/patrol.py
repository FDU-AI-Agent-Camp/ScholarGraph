"""Community patrol report schemas (BE-4) — aligned with docs/api/openapi.yaml."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class PatrolMode(StrEnum):
    LENS_CLASH = "lens_clash"
    CONTRADICTION = "contradiction"
    METHOD_OVERLAP = "method_overlap"
    CLAIM_EVOLUTION = "claim_evolution"


class PatrolInsightStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"


class NodeRef(BaseModel):
    paper_id: str
    node_id: str
    label: str | None = None


class PatrolPoint(BaseModel):
    """Base for all structured patrol points; discriminator is ``mode``."""

    mode: Literal["contradiction", "lens_clash", "method_overlap", "claim_evolution"]


class ContradictionPoint(PatrolPoint):
    mode: Literal["contradiction"]
    point_a: str
    point_b: str
    conflict_type: str


class LensClashPoint(PatrolPoint):
    mode: Literal["lens_clash"]
    lens_a: str
    lens_b: str
    clash_aspect: str


class MethodOverlapPoint(PatrolPoint):
    mode: Literal["method_overlap"]
    method: str
    overlap_score: float | None = Field(
        default=None,
        description="Significance score of the overlap. 1.0 for literal label match; "
        "0.0-1.0 for semantic soft match; omitted when unavailable.",
    )
    overlap_type: Literal["literal", "semantic"] | None = Field(
        default=None,
        description="How the overlap was determined: literal label equality or semantic embedding similarity.",
    )
    paper_a_usage: str = Field(
        description="How paper A uses the method. MVP fallback '用于 {method}' until LLM extraction."
    )
    paper_b_usage: str = Field(
        description="How paper B uses the method. MVP fallback '用于 {method}' until LLM extraction."
    )
    dataset_a: str | None = None
    dataset_b: str | None = None


class ClaimEvolutionPoint(PatrolPoint):
    mode: Literal["claim_evolution"]
    research_question: str
    paper_a_claim: str
    paper_b_claim: str
    evidence_summary: str


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
    structured_points: list[
        Annotated[
            ContradictionPoint | LensClashPoint | MethodOverlapPoint | ClaimEvolutionPoint,
            Field(discriminator="mode"),
        ]
    ] = Field(default_factory=list)


class PatrolReport(BaseModel):
    mode: PatrolMode
    paper_ids: list[str]
    insights: list[PatrolInsight] = Field(default_factory=list)
    generated_at: datetime
