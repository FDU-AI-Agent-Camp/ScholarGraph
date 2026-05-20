"""Community patrol report schemas (BE-4)."""

from pydantic import BaseModel, Field


class PatrolInsight(BaseModel):
    insight_id: str
    title: str
    summary: str
    severity: str = Field(description="info | warning | critical")
    paper_ids: list[str] = Field(default_factory=list)


class PatrolReport(BaseModel):
    report_id: str
    title: str
    insights: list[PatrolInsight] = Field(default_factory=list)
