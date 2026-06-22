"""Build classifier-facing text slices from extracted PDF plain text (BE-1)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.ingest.classifier_signals import (
    _looks_like_journal_line,
    extract_conclusion_tail,
    extract_meta_info,
)
from backend.ingest.text_utils import normalize_for_sections, normalize_whitespace

# collaboration §4.1 / README: 标题、摘要、关键词、引言前几段
MAX_CLASSIFIER_INPUT_CHARS = 12_000
MAX_TITLE_CHARS = 800
MAX_SECTION_BODY_CHARS = 4_000
MAX_INTRO_BODY_CHARS = 4_000
MIN_IMPLICIT_ABSTRACT_CHARS = 100
INTRO_SENTENCE_LIMIT = 8

_ABSTRACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?is)\babstract\b\s*[:\-]?\s*(.+?)(?=\n(?:keywords?|key\s*words|index\s*terms|"
        r"introduction|\d+\s*[\.\)]\s*introduction|references|acknowledgments)\b|\Z)",
    ),
    re.compile(
        r"(?is)摘\s*要\s*[：:]\s*(.+?)(?=\n(?:关键词|关键字|引言|前言|一[、．.\s]|"
        r"1[\s、．.]|参考文献)\b|\Z)",
    ),
)

_KEYWORDS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?is)\bkeywords?\b\s*[:\-]?\s*(.+?)(?=\n(?:introduction|\d+\s*[\.\)]|"
        r"references|acknowledgments)\b|\Z)",
    ),
    re.compile(
        r"(?is)关\s*键\s*词\s*[：:]\s*(.+?)(?=\n(?:引言|前言|一[、．.\s]|1[\s、．.]|参考文献)\b|\Z)",
    ),
)

_INTRO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?is)\bintroduction\b\s*(.+?)(?=\n(?:\d+\s*[\.\)]\s*(?:related|background|"
        r"methods|materials)|references)\b|\Z)",
    ),
    re.compile(
        r"(?is)(?:一[、．.\s]*(?:前\s*言|引\s*言)|引\s*言)\s*(.+?)(?=\n(?:二[、．.]|"
        r"2[\s、．.]|参考文献)\b|\Z)",
    ),
    re.compile(r"(?is)前\s*言\s*(.+?)(?=\n(?:二[、．.]|2[\s、．.]|参考文献)\b|\Z)"),
)


def _looks_like_author_line(line: str) -> bool:
    stripped = line.strip().lstrip("□")
    # Do not mistake a short journal name (e.g., "西夏研究") for an author line.
    if _looks_like_journal_line(line):
        return False
    # Western-style author lines.
    if re.search(
        r"(?:\d+,\d+|&|\bUniversity\b|\bCollege\b|\bDepartment\b|\bChina\.|\bet al\b|\^[0-9])",
        line,
    ):
        return True
    # Chinese author names: a short line of 2-4 Chinese characters (optional □ marker).
    if re.match(r"^[\u4e00-\u9fa5]{2,4}$", stripped):
        return True
    return False


def _looks_like_body_start(line: str) -> bool:
    return line.startswith(
        (
            "The development",
            "In recent",
            "In this",
            "Recently,",
            "Background",
            "Introduction",
            "本文",
            "本研究",
        )
    )


def _infer_lead_abstract(text: str) -> str | None:
    """Capture summary paragraph when publishers omit an 'Abstract' heading."""
    lines = text.split("\n")
    start: int | None = None
    for index, line in enumerate(lines):
        if index < 3:
            continue
        if _looks_like_author_line(line):
            continue
        if len(line) >= 80 and line[0].isupper():
            start = index
            break
    if start is None:
        return None

    parts: list[str] = []
    for line in lines[start:]:
        if parts and _looks_like_body_start(line):
            break
        parts.append(line)
        if len(" ".join(parts)) >= MAX_SECTION_BODY_CHARS:
            break

    body = " ".join(parts).strip()
    if len(body) < MIN_IMPLICIT_ABSTRACT_CHARS:
        return None
    return body[:MAX_SECTION_BODY_CHARS]


def _infer_intro_after_abstract(text: str, abstract: str) -> str | None:
    anchor = abstract[-min(80, len(abstract)) :]
    anchor_index = text.find(anchor)
    if anchor_index < 0:
        return None
    tail = text[anchor_index + len(anchor) :].strip()
    if not tail:
        return None

    normalized = " ".join(tail.split())
    sentences = re.split(r"(?<=[。！？.!?])\s+", normalized)
    selected = [sentence for sentence in sentences if sentence.strip()][:INTRO_SENTENCE_LIMIT]
    if not selected:
        return None
    joined = " ".join(selected)
    return joined[:MAX_INTRO_BODY_CHARS]


def _first_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            body = normalize_whitespace(match.group(1))
            if body:
                return body[:MAX_SECTION_BODY_CHARS]
    return None


def _extract_title(text: str) -> str:
    """Heuristic title: early non-boilerplate lines before abstract-like markers."""
    lines: list[str] = []
    for raw_line in text.split("\n")[:40]:
        line = raw_line.strip()
        if not line:
            if lines:
                break
            continue
        lower = line.lower()
        if lower.startswith(("http", "doi:", "article", "received:", "accepted:", "check for updates")):
            continue
        if re.match(r"^[\d\.\s]+$", line):
            continue
        if re.search(r"摘\s*要|abstract", line, re.IGNORECASE):
            break
        if _looks_like_author_line(line):
            break
        lines.append(line)
        if sum(len(part) for part in lines) >= MAX_TITLE_CHARS:
            break
    title = " ".join(lines)
    return title[:MAX_TITLE_CHARS]


def _trim_intro_paragraphs(body: str, *, max_paragraphs: int = 3) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    selected = paragraphs[:max_paragraphs]
    joined = "\n\n".join(selected)
    return joined[:MAX_INTRO_BODY_CHARS]


@dataclass(frozen=True)
class ClassifierSections:
    """Structured title / abstract / keywords / intro / conclusion / meta for head merge."""

    title: str = ""
    abstract: str = ""
    keywords: str = ""
    intro: str = ""
    conclusion: str = ""
    journal: str = ""
    funding: str = ""
    affiliation: str = ""


_TITLE_SECTION_RE = re.compile(
    r"(?is)\ATitle:\s*(.+?)(?=\n\nAbstract:|\n\nKeywords:|\n\nIntroduction:|\n\nConclusion:|\n\nMeta-Information:|\Z)",
)
_ABSTRACT_SECTION_RE = re.compile(
    r"(?is)\n\nAbstract:\s*(.+?)(?=\n\nKeywords:|\n\nIntroduction:|\n\nConclusion:|\n\nMeta-Information:|\Z)",
)
_KEYWORDS_SECTION_RE = re.compile(
    r"(?is)\n\nKeywords:\s*(.+?)(?=\n\nIntroduction:|\n\nConclusion:|\n\nMeta-Information:|\Z)",
)
_INTRO_SECTION_RE = re.compile(
    r"(?is)\n\nIntroduction:\s*(.+?)(?=\n\nConclusion:|\n\nMeta-Information:|\Z)",
)
_CONCLUSION_SECTION_RE = re.compile(
    r"(?is)\n\nConclusion:\s*(.+?)(?=\n\nMeta-Information:|\Z)",
)
_META_SECTION_RE = re.compile(r"(?is)\n\nMeta-Information:\s*(.+)\Z")


def _parse_meta_block(meta_text: str) -> dict[str, str]:
    """Parse labeled meta lines such as ``Journal: ...`` from the formatted block."""
    mapping: dict[str, str] = {}
    if not meta_text:
        return mapping
    for line in meta_text.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_clean = key.strip().lower()
        value_clean = value.strip()
        if key_clean in {"journal", "funding", "affiliation"} and value_clean:
            mapping[key_clean] = value_clean
    return mapping


def parse_classifier_sections(classifier_input: str) -> ClassifierSections:
    """Parse labeled classifier text produced by ``format_classifier_input``."""
    text = classifier_input.strip()
    if not text:
        return ClassifierSections()
    title_match = _TITLE_SECTION_RE.search(text)
    abstract_match = _ABSTRACT_SECTION_RE.search(text)
    keywords_match = _KEYWORDS_SECTION_RE.search(text)
    intro_match = _INTRO_SECTION_RE.search(text)
    conclusion_match = _CONCLUSION_SECTION_RE.search(text)
    meta_match = _META_SECTION_RE.search(text)
    if not any((title_match, abstract_match, keywords_match, intro_match, conclusion_match, meta_match)):
        return ClassifierSections()

    meta = _parse_meta_block(meta_match.group(1)) if meta_match else {}
    return ClassifierSections(
        title=normalize_whitespace(title_match.group(1)) if title_match else "",
        abstract=normalize_whitespace(abstract_match.group(1)) if abstract_match else "",
        keywords=normalize_whitespace(keywords_match.group(1)) if keywords_match else "",
        intro=intro_match.group(1).strip() if intro_match else "",
        conclusion=conclusion_match.group(1).strip() if conclusion_match else "",
        journal=meta.get("journal", ""),
        funding=meta.get("funding", ""),
        affiliation=meta.get("affiliation", ""),
    )


def extract_sections_from_text(full_text: str) -> ClassifierSections:
    """Extract header sections and lightweight meta signals from plain PDF text."""
    text = normalize_for_sections(full_text)
    if not text:
        return ClassifierSections()

    abstract = _first_match(_ABSTRACT_PATTERNS, text) or _infer_lead_abstract(text)
    keywords = _first_match(_KEYWORDS_PATTERNS, text)
    intro_raw = _first_match(_INTRO_PATTERNS, text)
    if intro_raw is None and abstract:
        intro_raw = _infer_intro_after_abstract(text, abstract)

    intro = _trim_intro_paragraphs(intro_raw) if intro_raw else ""
    meta = extract_meta_info(text)
    return ClassifierSections(
        title=_extract_title(text),
        abstract=abstract or "",
        keywords=keywords or "",
        intro=intro,
        journal=meta.get("journal", ""),
        funding=meta.get("funding", ""),
        affiliation=meta.get("affiliation", ""),
    )


def _format_meta_block(
    *,
    journal: str = "",
    funding: str = "",
    affiliation: str = "",
) -> str:
    lines: list[str] = []
    if journal.strip():
        lines.append(f"Journal: {journal.strip()}")
    if affiliation.strip():
        lines.append(f"Affiliation: {affiliation.strip()}")
    if funding.strip():
        lines.append(f"Funding: {funding.strip()}")
    if not lines:
        return ""
    return "Meta-Information:\n" + "\n".join(lines)


def format_classifier_input(
    *,
    title: str = "",
    abstract: str = "",
    keywords: str = "",
    intro: str = "",
    conclusion: str = "",
    journal: str = "",
    funding: str = "",
    affiliation: str = "",
) -> str:
    """Compose labeled classifier input aligned with paradigm classification prompts."""
    parts: list[str] = []
    meta_block = _format_meta_block(journal=journal, funding=funding, affiliation=affiliation)
    if meta_block:
        parts.append(meta_block)
    if title.strip():
        parts.append(f"Title: {title.strip()}")
    if abstract.strip():
        parts.append(f"Abstract: {abstract.strip()}")
    if keywords.strip():
        parts.append(f"Keywords: {keywords.strip()}")
    # Conclusion is placed before the often-lengthy introduction so that truncation
    # preserves this high-value paradigm signal.
    if conclusion.strip():
        parts.append(f"Conclusion:\n{conclusion.strip()}")
    if intro.strip():
        parts.append(f"Introduction:\n{intro.strip()}")

    combined = "\n\n".join(parts).strip()
    if not combined:
        return ""
    if len(combined) > MAX_CLASSIFIER_INPUT_CHARS:
        return combined[:MAX_CLASSIFIER_INPUT_CHARS].rstrip()
    return combined


def build_classifier_input(head_text: str, *, full_text: str | None = None) -> str:
    """
    Compose title + abstract + keywords + introduction + conclusion + meta for classification.

    Falls back to the document head when section markers are missing (e.g. cover pages).
    When ``full_text`` is supplied, the conclusion section is anchor-extracted from the tail.
    """
    sections = extract_sections_from_text(head_text)
    conclusion = extract_conclusion_tail(full_text) if full_text else ""

    has_core = any((sections.abstract, sections.keywords, sections.intro, conclusion))
    if not has_core:
        text = normalize_for_sections(head_text)
        return text[:MAX_CLASSIFIER_INPUT_CHARS].strip() if text else ""

    return format_classifier_input(
        title=sections.title,
        abstract=sections.abstract,
        keywords=sections.keywords,
        intro=sections.intro,
        conclusion=conclusion,
        journal=sections.journal,
        funding=sections.funding,
        affiliation=sections.affiliation,
    )
