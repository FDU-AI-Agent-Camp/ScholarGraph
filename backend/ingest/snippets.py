"""Build classifier-facing text slices from extracted PDF plain text (BE-1)."""

from __future__ import annotations

import re

# collaboration §4.1 / README: 标题、摘要、关键词、引言前几段
MAX_CLASSIFIER_INPUT_CHARS = 12_000
MAX_TITLE_CHARS = 800
MAX_SECTION_BODY_CHARS = 4_000
MAX_INTRO_BODY_CHARS = 4_000
MIN_IMPLICIT_ABSTRACT_CHARS = 100
INTRO_SENTENCE_LIMIT = 8

_WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")

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


def normalize_for_sections(text: str) -> str:
    """Preserve line breaks for section headers while trimming horizontal noise."""
    if not text:
        return ""
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _WHITESPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces and excessive blank lines (full-text export)."""
    section_text = normalize_for_sections(text)
    if not section_text:
        return ""
    return _BLANK_LINES_RE.sub("\n\n", section_text.replace("\n", "\n\n")).strip()


def _looks_like_author_line(line: str) -> bool:
    return bool(
        re.search(
            r"(?:\d+,\d+|&|\bUniversity\b|\bCollege\b|\bDepartment\b|\bChina\.|\bet al\b|\^[0-9])",
            line,
        )
    )


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


def build_classifier_input(full_text: str) -> str:
    """
    Compose title + abstract + keywords + introduction opening for paradigm classification.

    Falls back to the document head when section markers are missing (e.g. cover pages).
    """
    text = normalize_for_sections(full_text)
    if not text:
        return ""

    abstract = _first_match(_ABSTRACT_PATTERNS, text) or _infer_lead_abstract(text)
    keywords = _first_match(_KEYWORDS_PATTERNS, text)
    intro_raw = _first_match(_INTRO_PATTERNS, text)
    if intro_raw is None and abstract:
        intro_raw = _infer_intro_after_abstract(text, abstract)

    if not any((abstract, keywords, intro_raw)):
        return text[:MAX_CLASSIFIER_INPUT_CHARS].strip()

    parts: list[str] = []
    title = _extract_title(text)
    if title:
        parts.append(f"Title: {title}")

    if abstract:
        parts.append(f"Abstract: {abstract}")

    if keywords:
        parts.append(f"Keywords: {keywords}")

    if intro_raw:
        parts.append(f"Introduction:\n{_trim_intro_paragraphs(intro_raw)}")

    combined = "\n\n".join(parts).strip()
    if len(combined) > MAX_CLASSIFIER_INPUT_CHARS:
        return combined[:MAX_CLASSIFIER_INPUT_CHARS].rstrip()
    return combined
