"""Community patrol report schemas (BE-4) — aligned with docs/api/openapi.yaml."""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, computed_field, model_validator


class PatrolMode(StrEnum):
    LENS_CLASH = "lens_clash"
    CONTRADICTION = "contradiction"
    METHOD_OVERLAP = "method_overlap"
    CLAIM_EVOLUTION = "claim_evolution"


class PatrolInsightStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"


class PatrolDegradationReason(StrEnum):
    """Machine-readable reasons why Patrol RAG context was thinned."""

    INDEX_NOT_READY = "INDEX_NOT_READY"
    QUERY_FAILED = "QUERY_FAILED"
    VECTOR_STORE_UNAVAILABLE = "VECTOR_STORE_UNAVAILABLE"


class PatrolDegradationSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"


class PatrolDegradationComponent(StrEnum):
    RAG_CONTEXT = "RAG_CONTEXT"


class PatrolDegradationProfile(BaseModel):
    """First-class degradation contract for thin RAG context (P9 / F8)."""

    component: PatrolDegradationComponent = Field(
        default=PatrolDegradationComponent.RAG_CONTEXT,
        description="Which subsystem degraded; currently always RAG_CONTEXT.",
    )
    reason_code: PatrolDegradationReason = Field(
        ...,
        description="Typed degradation reason — INDEX_NOT_READY / QUERY_FAILED / VECTOR_STORE_UNAVAILABLE.",
    )
    affected_papers: list[str] = Field(
        default_factory=list,
        description="Paper IDs whose vector index was missing or whose chunk query failed.",
    )
    severity: PatrolDegradationSeverity = Field(
        default=PatrolDegradationSeverity.WARNING,
        description="UI severity hint; VECTOR_STORE_UNAVAILABLE maps to ERROR.",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp when the degradation was recorded.",
    )


class PatrolExclusionReason(StrEnum):
    """Machine-readable reasons for channel-B ``insufficient_data`` conclusions (P11)."""

    MISSING_REQUIRED_NODES = "MISSING_REQUIRED_NODES"
    PARADIGM_UNSUPPORTED = "PARADIGM_UNSUPPORTED"
    NO_OVERLAP = "NO_OVERLAP"
    RQ_GATE_FAILED = "RQ_GATE_FAILED"
    NO_RECALLABLE_CLAIMS = "NO_RECALLABLE_CLAIMS"


class PatrolExclusionLogic(BaseModel):
    """Why a completed Patrol run concluded with insufficient_data (negative determination)."""

    phase: str = Field(
        ...,
        description=(
            "Pipeline stage where the exclusion fired (e.g. PARADIGM_GATE, NODE_PRECHECK, OVERLAP_MATCH, RQ_ALIGNMENT)."
        ),
    )
    reason_code: PatrolExclusionReason = Field(
        ...,
        description="Typed exclusion reason for FE warning-card copy routing.",
    )
    description: str = Field(
        ...,
        description="Human-readable explanation of the negative determination.",
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional diagnostic numbers (thresholds, scores, counts).",
    )


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
        description="Whether the point compares methods or datasets (dual overlap emits two points).",
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
    node_refs: list[NodeRef] = Field(
        default_factory=list,
        description="Graph nodes anchored by this point; supports many-to-many literal overlaps.",
    )
    paper_a_usage: str = Field(description="How paper A uses the overlapping item.")
    paper_b_usage: str = Field(description="How paper B uses the overlapping item.")
    dataset_a: str | None = None
    dataset_b: str | None = None
    evidence_summary: str | None = Field(
        default=None,
        description="基于双方方法/数据证据链的综合摘要；LLM 未生成时可为空。",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def method(self) -> str:
        """Deprecated alias for ``overlap_label``; kept for legacy frontend consumers."""
        return self.overlap_label

    model_config = {"populate_by_name": True}


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
            "Insight readiness status. 'insufficient_data' is a conclusive channel-B "
            "negative determination (HTTP 200), not an API error — see exclusion_logic."
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
    is_degraded: bool = Field(
        default=False,
        description="True when RAG context was thinned; prefer degradation_profile over meta.",
    )
    degradation_profile: PatrolDegradationProfile | None = Field(
        default=None,
        description="Explicit RAG degradation contract when is_degraded is true.",
    )
    exclusion_logic: PatrolExclusionLogic | None = Field(
        default=None,
        description=(
            "Required when status='insufficient_data': structured reason for the negative determination (P11 / F7)."
        ),
    )
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Legacy machine-readable metadata. Prefer is_degraded + degradation_profile; "
            "meta.patrol_rag_context_degraded remains a compatibility mirror."
        ),
    )

    @model_validator(mode="after")
    def _require_exclusion_logic_for_insufficient_data(self) -> Self:
        if self.status == PatrolInsightStatus.INSUFFICIENT_DATA and self.exclusion_logic is None:
            msg = "exclusion_logic is required when status is insufficient_data"
            raise ValueError(msg)
        return self


class PatrolReport(BaseModel):
    mode: PatrolMode
    paper_ids: list[str]
    insights: list[PatrolInsight] = Field(default_factory=list)
    generated_at: datetime
