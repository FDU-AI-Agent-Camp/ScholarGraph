"""Integration: real ingest PDF extraction → structured classifier input (BE-1)."""

from __future__ import annotations

import pytest
from backend.ingest.pdf import extract_pdf_text, ingest_pdf
from backend.ingest.snippets import build_classifier_input

pytestmark = pytest.mark.integration


def test_structured_pdf_extract_then_build_classifier_input(structured_stem_pdf) -> None:
    full_text = extract_pdf_text(structured_stem_pdf)
    snippet = build_classifier_input(full_text)

    assert "Transformer Model for Crystal Properties" in full_text
    assert "Title:" in snippet
    assert "Abstract:" in snippet
    assert "Keywords:" in snippet
    assert "Introduction:" in snippet
    assert "machine learning" in snippet


async def test_ingest_pdf_matches_extract_plus_snippet_pipeline(structured_stem_pdf) -> None:
    result = await ingest_pdf(structured_stem_pdf, paper_id="pipeline-check")

    assert result["paper_id"] == "pipeline-check"
    assert "materials science" in result["full_text"]
    assert "Keywords:" in result["classifier_input"]
    assert len(result["classifier_input"]) <= len(result["full_text"])
