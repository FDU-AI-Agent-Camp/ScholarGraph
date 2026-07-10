"""Structured LLM outputs for patrol insight summaries (BE-4)."""

from pydantic import BaseModel, Field


class PatrolSummaryOutput(BaseModel):
    """JSON-schema constrained patrol summary returned by the LLM."""

    summary: str = Field(
        ...,
        min_length=20,
        max_length=600,
        description="中文巡检洞察摘要，客观描述两篇论文的可比差异或论证张力",
    )


class ClaimEvolutionOutput(BaseModel):
    """Structured NLI-style output for claim_evolution patrol mode."""

    evolution_type: str = Field(
        ...,
        pattern=r"^(inherit|contradict|refined)$",
        description="演进类型：inherit（继承深化）、contradict（矛盾冲突）、refined（修正细化）",
    )
    problem_fit_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="两篇论文研究问题契合度评分，0-100",
    )
    comparison_summary: str = Field(
        ...,
        min_length=20,
        max_length=600,
        description="中文观点对比摘要，说明两篇论文结论的演进或分歧关系",
    )
    evidence_summary: str | None = Field(
        default=None,
        max_length=800,
        description="基于双方证据链的综合摘要；LLM 未生成时可为空",
    )


class MethodComparativeDetail(BaseModel):
    """Per-method-pair structured comparison returned by the LLM for method_overlap mode."""

    method_pair_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        description="方法对名称，例如 'PCA <-> Principal Component Analysis'",
    )
    paper_a_usage: str = Field(
        ...,
        min_length=10,
        max_length=400,
        description="论文 A 中该方法的具体应用场景与工程改造",
    )
    paper_b_usage: str = Field(
        ...,
        min_length=10,
        max_length=400,
        description="论文 B 中该方法的具体应用场景与工程改造",
    )
    evidence_summary: str = Field(
        ...,
        min_length=10,
        max_length=600,
        description="核心重叠点与演进差异的精炼总结",
    )


class MethodOverlapOutput(BaseModel):
    """Structured output for method_overlap patrol mode."""

    summary: str = Field(
        ...,
        min_length=20,
        max_length=600,
        description="针对两篇论文方法论层面的宏观对比综述",
    )
    comparison_details: list[MethodComparativeDetail] = Field(
        ...,
        min_length=1,
        description="方法对比详情列表，每个元素对应一对显著重叠的方法",
    )


# Discriminated union of all mode-specific structured outputs from the patrol LLM layer.
# Callers select the concrete schema via ``PatrolMode`` rather than this union directly,
# but the union documents the closed set of valid return types for type-checking.
PatrolStructuredOutput = PatrolSummaryOutput | ClaimEvolutionOutput | MethodOverlapOutput
