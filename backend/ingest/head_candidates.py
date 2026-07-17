# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Build path-A / path-B head field candidates for merge (§2.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.ingest.pdf import CLASSIFIER_HEAD_PAGE_LIMIT, extract_pdf_text
from backend.ingest.snippets import (
    ClassifierSections,
    extract_conclusion_tail,
    extract_meta_info,
    extract_sections_from_text,
    normalize_for_sections,
    normalize_whitespace,
    parse_classifier_sections,
)

_MD_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_MD_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_MD_ABSTRACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?is)(?:^|\n)#+\s*abstract\s*\n+(.+?)(?=\n#+\s|\Z)",
    ),
    re.compile(
        r"(?is)(?:^|\n)#+\s*摘\s*要\s*\n+(.+?)(?=\n#+\s|\Z)",
    ),
    re.compile(r"(?is)\babstract\b\s*[:\-]?\s*(.+?)(?=\n(?:keywords?|introduction|\#+\s)|\Z)"),
    re.compile(r"(?is)摘\s*要\s*[：:]\s*(.+?)(?=\n(?:关键词|引言|#+\s)|\Z)"),
)
_MD_KEYWORDS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?is)(?:^|\n)#+\s*keywords?\s*\n+(.+?)(?=\n#+\s|\Z)"),
    re.compile(r"(?is)keywords?\s*[:\-]\s*(.+?)(?=\n(?:introduction|\#+\s)|\Z)"),
    re.compile(r"(?is)关键词\s*[：:]\s*(.+?)(?=\n(?:引言|#+\s)|\Z)"),
)


@dataclass(frozen=True)
class HeadCandidate:
    """Single-source header fields before merge."""

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
    source: str = "pymupdf"

    @classmethod
    def from_sections(cls, sections: ClassifierSections, *, source: str) -> HeadCandidate:
        return cls(
            title=sections.title,
            abstract=sections.abstract,
            keywords=sections.keywords,
            intro=sections.intro,
            conclusion=sections.conclusion,
            journal=sections.journal,
            funding=sections.funding,
            affiliation=sections.affiliation,
            research_object=sections.research_object,
            methodology_tool=sections.methodology_tool,
            core_intellectual_contribution=sections.core_intellectual_contribution,
            source=source,
        )

    @classmethod
    def from_classifier_input(cls, classifier_input: str, *, source: str = "pymupdf") -> HeadCandidate:
        return cls.from_sections(parse_classifier_sections(classifier_input), source=source)


def build_pymupdf_head_candidate(pdf_path: Path) -> HeadCandidate:
    """Path A: PyMuPDF head pages → structured sections."""
    head_text = extract_pdf_text(pdf_path, max_pages=CLASSIFIER_HEAD_PAGE_LIMIT)
    return HeadCandidate.from_sections(extract_sections_from_text(head_text), source="pymupdf")


def _first_md_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            body = normalize_whitespace(match.group(1))
            if body:
                return body
    return None


def _extract_markdown_intro(md: str) -> str:
    """First non-metadata ``##`` section body."""
    skip = re.compile(r"(?i)abstract|摘要|keywords?|关键词|references|参考文献")
    for match in _MD_H2_RE.finditer(md):
        heading = match.group(1).strip()
        if skip.search(heading):
            continue
        start = match.end()
        tail = md[start:].lstrip("\n")
        next_heading = re.search(r"(?m)^##\s+", tail)
        body = tail[: next_heading.start()] if next_heading else tail
        return body.strip()[:4_000]
    return ""


def parse_mineru_markdown(md_text: str) -> HeadCandidate:
    """Path B (short PDF): MinerU pipeline markdown → header fields."""
    text = normalize_for_sections(md_text)
    title_match = _MD_TITLE_RE.search(text)
    title = normalize_whitespace(title_match.group(1)) if title_match else ""
    abstract = _first_md_match(_MD_ABSTRACT_PATTERNS, text) or ""
    keywords = _first_md_match(_MD_KEYWORDS_PATTERNS, text) or ""
    intro = _extract_markdown_intro(text)
    meta = extract_meta_info(text)
    conclusion = extract_conclusion_tail(md_text) if md_text else ""
    return HeadCandidate(
        title=title,
        abstract=abstract,
        keywords=keywords,
        intro=intro,
        conclusion=conclusion,
        journal=meta.get("journal", ""),
        funding=meta.get("funding", ""),
        affiliation=meta.get("affiliation", ""),
        source="mineru",
    )
