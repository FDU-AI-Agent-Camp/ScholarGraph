# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""P11 unit: merge_with_rules records per-field sources for audit."""

from __future__ import annotations

from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.head_merge import merge_with_rules


def test_short_pdf_prefers_mineru_and_tags_sources() -> None:
    snippets = HeadCandidate(
        title="Noisy Title",
        abstract="Snippet abstract",
        source="pymupdf",
    )
    mineru = HeadCandidate(
        title="Clean Title",
        abstract="MinerU abstract",
        source="mineru",
    )

    merged = merge_with_rules(snippets, mineru, is_short=True)

    assert merged.title == "Clean Title"
    assert merged.sources["title"] == "mineru"
    assert merged.sources["abstract"] == "mineru"


def test_long_pdf_prefers_grobid_and_falls_back_to_snippets() -> None:
    snippets = HeadCandidate(
        title="Snippet Title",
        abstract="",
        keywords="kw-from-pymupdf",
        source="pymupdf",
    )
    grobid = HeadCandidate(
        title="GROBID Title",
        abstract="GROBID abstract",
        keywords="",
        source="grobid",
    )

    merged = merge_with_rules(snippets, grobid, is_short=False)

    assert merged.title == "GROBID Title"
    assert merged.abstract == "GROBID abstract"
    assert merged.keywords == "kw-from-pymupdf"
    assert merged.sources["title"] == "grobid"
    assert merged.sources["abstract"] == "grobid"
    assert merged.sources["keywords"] == "pymupdf"


def test_missing_path_b_marks_empty_fields() -> None:
    snippets = HeadCandidate(title="", abstract="", source="pymupdf")

    merged = merge_with_rules(snippets, None, is_short=True)

    assert merged.title == ""
    assert merged.sources["title"] == "empty"
