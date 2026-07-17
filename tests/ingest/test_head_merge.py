# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Head merge rules and markdown candidate parsing."""

from __future__ import annotations

import pytest
from backend.ingest.head_candidates import HeadCandidate, parse_mineru_markdown
from backend.ingest.head_merge import merge_with_rules


def test_parse_mineru_markdown_extracts_sections() -> None:
    md = """# Deep Learning Survey

## Abstract

We review recent advances in deep learning.

## Keywords

neural networks, transformers

## Introduction

This paper surveys the field.
"""
    candidate = parse_mineru_markdown(md)
    assert candidate.title == "Deep Learning Survey"
    assert "deep learning" in candidate.abstract.lower()
    assert "neural networks" in candidate.keywords
    assert "surveys the field" in candidate.intro


def test_merge_with_rules_short_prefers_mineru() -> None:
    snippets = HeadCandidate(
        title="Snippet Title",
        abstract="Snippet abstract",
        keywords="a",
        intro="Snippet intro",
        source="pymupdf",
    )
    mineru = HeadCandidate(
        title="MinerU Title",
        abstract="MinerU abstract",
        keywords="b",
        intro="MinerU intro",
        source="mineru",
    )
    merged = merge_with_rules(snippets, mineru, is_short=True)
    assert merged.title == "MinerU Title"
    assert merged.abstract == "MinerU abstract"
    assert merged.sources["title"] == "mineru"


def test_merge_with_rules_long_prefers_grobid() -> None:
    snippets = HeadCandidate(title="Snippet Title", source="pymupdf")
    grobid = HeadCandidate(title="GROBID Title", abstract="GROBID abs", source="grobid")
    merged = merge_with_rules(snippets, grobid, is_short=False)
    assert merged.title == "GROBID Title"
    assert merged.abstract == "GROBID abs"
    assert merged.sources["abstract"] == "grobid"


def test_merge_with_rules_falls_back_to_snippets_when_path_b_missing() -> None:
    snippets = HeadCandidate(title="Only Snippet", abstract="Abs", source="pymupdf")
    merged = merge_with_rules(snippets, None, is_short=True)
    assert merged.title == "Only Snippet"
    assert merged.sources["title"] == "pymupdf"


def test_merge_with_rules_carries_core_contribution_fields() -> None:
    snippets = HeadCandidate(
        title="A",
        research_object="ancient populations",
        methodology_tool="GIS",
        core_intellectual_contribution="historical migration pattern",
        source="pymupdf",
    )
    grobid = HeadCandidate(
        title="B",
        abstract="abs",
        research_object="",
        methodology_tool="",
        core_intellectual_contribution="",
        source="grobid",
    )
    merged = merge_with_rules(snippets, grobid, is_short=False)
    assert merged.title == "B"
    assert merged.research_object == "ancient populations"
    assert merged.methodology_tool == "GIS"
    assert merged.core_intellectual_contribution == "historical migration pattern"
    assert "Research Object:" in merged.to_classifier_input()
    assert "Methodology/Tool:" in merged.to_classifier_input()
    assert "Core Intellectual Contribution:" in merged.to_classifier_input()


@pytest.mark.asyncio
async def test_merge_head_candidates_uses_rules_in_mock_mode() -> None:
    from backend.config import Settings
    from backend.ingest.head_merge import merge_head_candidates

    snippets = HeadCandidate(title="A", source="pymupdf")
    path_b = HeadCandidate(title="B", source="mineru")
    settings = Settings(_env_file=None, llm_mode="mock", ingest_head_llm_enabled=True)
    merged = await merge_head_candidates(snippets, path_b, is_short=True, settings=settings)
    assert merged.title == "B"
