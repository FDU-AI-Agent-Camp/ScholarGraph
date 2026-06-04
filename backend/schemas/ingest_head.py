"""Structured document head fields for ingest routing and LLM merge."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngestHead(BaseModel):
    """Title / abstract / keywords / intro with per-field provenance."""

    title: str = ""
    abstract: str = ""
    keywords: str = ""
    intro: str = ""
    sources: dict[str, str] = Field(default_factory=dict)

    def to_classifier_input(self) -> str:
        from backend.ingest.snippets import format_classifier_input

        return format_classifier_input(
            title=self.title,
            abstract=self.abstract,
            keywords=self.keywords,
            intro=self.intro,
        )
