"""Community patrol report schemas (BE-4) — aligned with docs/api/openapi.yaml."""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_serializer


class PatrolMode(StrEnum):
    LENS_CLASH = "lens_clash"
    CONTRADICTION = "contradiction"
    METHOD_OVERLAP = "method_overlap"
    CLAIM_EVOLUTION = "claim_evolution"


class PatrolInsightStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"


class EvolutionType(StrEnum):
    """Relationship between two claims addressing the same research question."""

    INHERIT = "inherit"
    CONTRADICT = "contradict"
    REFINED = "refined"


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


class OverlapType(StrEnum):
    """What kind of item is being compared in a method_overlap point."""

    METHOD = "method"
    DATASET = "dataset"
    MIXED = "mixed"


class MethodOverlapPoint(PatrolPoint):
    mode: Literal["method_overlap"]
    overlap_type: OverlapType = Field(
        ...,
        description="Whether the point compares methods, datasets, or both.",
    )
    overlap_label: str = Field(
        ...,
        description="The representative label of the overlapping item (method or dataset name).",
    )
    overlap_score: float | None = Field(
        default=None,
        description="Significance score of the overlap. 1.0 for literal label match; "
        "0.0-1.0 for semantic soft match; omitted when unavailable.",
    )
    match_type: Literal["literal", "semantic"] | None = Field(
        default=None,
        description="How the overlap was determined: literal label equality or semantic embedding similarity.",
    )
    paper_a_usage: str = Field(description="How paper A uses the overlapping item.")
    paper_b_usage: str = Field(description="How paper B uses the overlapping item.")
    dataset_a: str | None = None
    dataset_b: str | None = None
    evidence_summary: str | None = Field(
        default=None,
        description="基于双方方法/数据证据链的综合摘要；LLM 未生成时可为空。",
    )

    # Backwards-compatible alias kept for consumers that expect the old ``method`` field.
    # TODO: remove once frontend and fixtures have migrated to ``overlap_label``.
    @property
    def method(self) -> str:
        """Return the overlap label for legacy callers expecting a ``method`` field."""
        return self.overlap_label

    model_config = {"populate_by_name": True}

    @model_serializer(mode="wrap")
    def _serialize_with_method(self, handler):
        data = handler(self)
        data["method"] = self.method
        return data


class ClaimEvolutionPoint(PatrolPoint):
    mode: Literal["claim_evolution"]
    research_question: str
    paper_a_claim: str | None = Field(
        default=None,
        description="论文 A 的核心结论；当图谱未抽取到 Claim 节点时，可从 VectorStore 召回文本填充。",
    )
    paper_b_claim: str | None = Field(
        default=None,
        description="论文 B 的核心结论；当图谱未抽取到 Claim 节点时，可从 VectorStore 召回文本填充。",
    )
    evolution_type: EvolutionType | None = Field(
        default=None,
        description="两篇论文结论的演进关系：inherit（继承深化）、contradict（矛盾冲突）、refined（修正细化）。",
    )
    problem_fit_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="研究问题契合度评分，0-100；数值越高说明两篇论文关注的问题越一致。",
    )
    evidence_summary: str | None = Field(
        default=None,
        description="基于双方证据链的综合摘要；LLM 未生成时可用召回 Chunk 文本作为兜底。",
    )


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
    structured_points: Sequence[
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
