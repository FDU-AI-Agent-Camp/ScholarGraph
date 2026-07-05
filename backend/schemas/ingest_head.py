"""Structured document head fields for ingest routing and LLM merge."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngestHead(BaseModel):
    """Title / abstract / keywords / intro / conclusion / meta / core contribution with per-field provenance."""

    title: str = ""
    abstract: str = ""
    keywords: str = ""
    intro: str = ""
    conclusion: str = ""
    journal: str = ""
    funding: str = ""
    affiliation: str = ""
    research_object: str = ""
    methodology_tool: str = ""
    core_intellectual_contribution: str = ""
    sources: dict[str, str] = Field(
        default_factory=dict,
        description="Per-field source tag: pymupdf, mineru, grobid, llm, empty, etc.",
    )

    def to_classifier_input(self) -> str:
        from backend.ingest.snippets import format_classifier_input

        return format_classifier_input(
            title=self.title,
            abstract=self.abstract,
            keywords=self.keywords,
            intro=self.intro,
            conclusion=self.conclusion,
            journal=self.journal,
            funding=self.funding,
            affiliation=self.affiliation,
            research_object=self.research_object,
            methodology_tool=self.methodology_tool,
            core_intellectual_contribution=self.core_intellectual_contribution,
        )


class PersistedHeadRefine(BaseModel):
    """On-disk head refine artifact (same lifecycle as UnifiedPaperGraph)."""

    paper_id: str
    merged: IngestHead
    classifier_input: str = ""
    warnings: list[str] = Field(default_factory=list)
