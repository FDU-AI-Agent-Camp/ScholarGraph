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
