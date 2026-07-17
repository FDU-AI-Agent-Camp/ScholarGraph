# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""GROBID TEI parser unit tests."""

from __future__ import annotations

from pathlib import Path

from backend.ingest.tei_parser import parse_tei_to_head_candidate

FIXTURE = Path(__file__).parent / "fixtures" / "grobid_sample.tei.xml"


def test_parse_tei_to_head_candidate_extracts_header_fields() -> None:
    tei = FIXTURE.read_text(encoding="utf-8")
    candidate = parse_tei_to_head_candidate(tei)

    assert candidate.source == "grobid"
    assert candidate.title == "Sample GROBID Title"
    assert "sample abstract" in candidate.abstract.lower()
    assert "graph" in candidate.keywords
    assert "introduction paragraph" in candidate.intro.lower()
    assert "Methods" not in candidate.intro
