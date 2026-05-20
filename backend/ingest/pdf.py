"""PDF parsing (BE-1)."""

from pathlib import Path
from typing import TypedDict


class IngestResult(TypedDict):
    paper_id: str
    full_text: str
    classifier_input: str


async def ingest_pdf(file_path: Path, paper_id: str | None = None) -> IngestResult:
    """Parse PDF and return full text plus classifier input snippet."""
    raise NotImplementedError("BE-1: implement PDF ingest in backend/ingest/pdf.py")
