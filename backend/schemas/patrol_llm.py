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
