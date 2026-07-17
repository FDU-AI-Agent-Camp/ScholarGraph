# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Long-paper chunking: section-aware splitting with head-context anchoring."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from backend.schemas.paradigm import Paradigm

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHUNK_CHARS = 12_000


@dataclass(frozen=True)
class TextChunk:
    """A contiguous slice of a paper used for anchored extraction."""

    index: int
    title: str | None
    text: str
    start_char: int
    end_char: int


# Section title patterns used to split academic papers into semantic chunks.
# Order matters: more specific multi-word titles appear before generic ones.
SECTION_TITLE_PATTERNS: dict[Paradigm, list[str]] = {
    Paradigm.STEM: [
        "Abstract",
        "Introduction",
        "Related Work",
        "Background",
        "Preliminaries",
        "Methodology",
        "Methods",
        "Model",
        "Architecture",
        "Experiments",
        "Experimental Setup",
        "Results",
        "Evaluation",
        "Discussion",
        "Ablation Study",
        "Conclusion",
        "Conclusions",
        "References",
        "Acknowledgements",
        "Appendix",
    ],
    Paradigm.HSS: [
        "Abstract",
        "Introduction",
        "Literature Review",
        "Theoretical Framework",
        "Conceptual Framework",
        "Methodology",
        "Methods",
        "Data",
        "Analysis",
        "Findings",
        "Discussion",
        "Implications",
        "Conclusion",
        "Conclusions",
        "References",
        "Acknowledgements",
        "Appendix",
    ],
}


def _build_section_regex(titles: list[str]) -> re.Pattern[str]:
    """Build a regex that matches common section header lines."""
    # Allow optional leading numbering like "1. " or "2.1 " or "I. "
    escaped = [re.escape(title) for title in titles]
    pattern = (
        r"^\s*(?:"
        r"(?:\d+(?:\.\d+)*\s+[.\-]?\s*)|"
        r"(?:[IVXivx]+\.\s*)"
        r")?(" + "|".join(escaped) + r")\s*(?:[:.\-]?\s*)*$"
    )
    return re.compile(pattern, re.MULTILINE | re.IGNORECASE)


def _split_by_sections(text: str, paradigm: Paradigm) -> list[tuple[str | None, str, int, int]]:
    """Split text into (title, section_text, start, end) tuples by section headers.

    If no headers are found, returns a single chunk with ``title=None``.
    """
    titles = SECTION_TITLE_PATTERNS[paradigm]
    regex = _build_section_regex(titles)
    matches = list(regex.finditer(text))

    if not matches:
        return [(None, text, 0, len(text))]

    sections: list[tuple[str | None, str, int, int]] = []
    # Treat text before the first match as a preamble chunk.
    first_match = matches[0]
    if first_match.start() > 0:
        preamble = text[: first_match.start()].strip()
        if preamble:
            sections.append((None, preamble, 0, first_match.start()))

    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        body_start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        section_text = text[body_start:end].strip()
        if section_text:
            sections.append((title, section_text, body_start, end))

    return sections


def _split_oversized(
    title: str | None,
    text: str,
    start_offset: int,
    max_chunk_chars: int,
    overlap_ratio: float = 0.0,
) -> list[TextChunk]:
    """Split a section that exceeds ``max_chunk_chars`` into paragraph/sentence chunks.

    When ``overlap_ratio > 0``, chunks are built with a content budget of
    ``max_chunk_chars - overlap_chars`` and then each chunk (except the first)
    is prefixed with the trailing ``overlap_chars`` of the previous chunk. This
    soft boundary keeps cross-boundary sentences/claims within a single chunk's
    context, reducing confidence decay in downstream extraction.
    """
    if len(text) <= max_chunk_chars:
        return [TextChunk(index=0, title=title, text=text, start_char=start_offset, end_char=start_offset + len(text))]

    overlap_chars = int(max_chunk_chars * overlap_ratio)
    content_budget = max_chunk_chars - overlap_chars
    if content_budget < 200:
        overlap_chars = 0
        content_budget = max_chunk_chars

    raw_chunks: list[TextChunk] = []
    # Prefer paragraph boundaries (double newlines).
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    current_text = ""
    current_start = start_offset
    for para in paragraphs:
        # If a single paragraph exceeds the content budget, split it by sentences.
        if len(para) > content_budget:
            if current_text:
                stripped = current_text.strip()
                raw_chunks.append(
                    TextChunk(
                        index=len(raw_chunks),
                        title=title,
                        text=stripped,
                        start_char=current_start,
                        end_char=current_start + len(stripped),
                    )
                )
                current_text = ""
            sentences = re.split(r"(?<=[.!?。！？])\s+", para)
            for sent in sentences:
                if len(current_text) + len(sent) + 1 > content_budget and current_text:
                    stripped = current_text.strip()
                    raw_chunks.append(
                        TextChunk(
                            index=len(raw_chunks),
                            title=title,
                            text=stripped,
                            start_char=current_start,
                            end_char=current_start + len(stripped),
                        )
                    )
                    current_text = ""
                    current_start = raw_chunks[-1].end_char + 1
                current_text += sent + " "
            continue

        if len(current_text) + len(para) + 2 > content_budget and current_text:
            stripped = current_text.strip()
            raw_chunks.append(
                TextChunk(
                    index=len(raw_chunks),
                    title=title,
                    text=stripped,
                    start_char=current_start,
                    end_char=current_start + len(stripped),
                )
            )
            current_text = ""
            current_start = raw_chunks[-1].end_char + 1
        current_text += para + "\n\n"

    if current_text.strip():
        stripped = current_text.strip()
        raw_chunks.append(
            TextChunk(
                index=len(raw_chunks),
                title=title,
                text=stripped,
                start_char=current_start,
                end_char=current_start + len(stripped),
            )
        )

    # Apply sliding-window overlap: each chunk after the first carries the tail
    # of the previous chunk so boundary-spanning claims stay in context.
    overlapped: list[TextChunk] = []
    for i, chunk in enumerate(raw_chunks):
        if i == 0 or overlap_chars <= 0:
            overlapped.append(chunk)
            continue
        prev_text = raw_chunks[i - 1].text
        prefix = prev_text[-overlap_chars:].strip() if len(prev_text) > overlap_chars else prev_text
        new_text = f"{prefix}\n\n{chunk.text}".strip()
        new_start = max(start_offset, chunk.start_char - len(prefix))
        overlapped.append(
            TextChunk(
                index=i,
                title=chunk.title,
                text=new_text,
                start_char=new_start,
                end_char=chunk.end_char,
            )
        )

    # Re-number indices sequentially.
    return [
        TextChunk(
            index=i,
            title=c.title,
            text=c.text,
            start_char=c.start_char,
            end_char=c.end_char,
        )
        for i, c in enumerate(overlapped)
    ]


def _merge_small_chunks(chunks: list[TextChunk], min_chunk_chars: int) -> list[TextChunk]:
    """Merge chunks smaller than ``min_chunk_chars`` into their neighbors.

    Tiny chunks (e.g. section headers or sparse pages) often confuse the node
    extractor because they contain no substantive content. Merging them with an
    adjacent chunk keeps the semantic boundary while ensuring enough text.
    """
    if not chunks:
        return []

    merged: list[TextChunk] = []
    for chunk in chunks:
        if len(chunk.text) < min_chunk_chars and merged:
            prev = merged[-1]
            combined_text = f"{prev.text}\n\n{chunk.text}".strip()
            merged[-1] = TextChunk(
                index=prev.index,
                title=prev.title,
                text=combined_text,
                start_char=prev.start_char,
                end_char=chunk.end_char,
            )
        else:
            merged.append(chunk)

    # If the first chunk itself is tiny and there is a second chunk, merge forward.
    if len(merged) >= 2 and len(merged[0].text) < min_chunk_chars:
        first, second = merged[0], merged[1]
        combined_text = f"{first.text}\n\n{second.text}".strip()
        merged[1] = TextChunk(
            index=second.index,
            title=second.title,
            text=combined_text,
            start_char=first.start_char,
            end_char=second.end_char,
        )
        merged.pop(0)

    return merged


def chunk_text(
    full_text: str,
    paradigm: Paradigm,
    *,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    min_chunk_chars: int = 500,
    overlap_ratio: float = 0.0,
) -> list[TextChunk]:
    """Split ``full_text`` into anchored chunks for long-paper extraction.

    The algorithm first attempts section-aware splitting (Introduction, Methods,
    Results, ...). Sections larger than ``max_chunk_chars`` are further split at
    paragraph and sentence boundaries. Tiny chunks are merged with neighbors to
    avoid empty extraction results. If no section headers are detected, the text
    falls back to a sliding-window split.

    A positive ``overlap_ratio`` creates a soft boundary between consecutive
    chunks by repeating the trailing context of chunk N at the start of chunk
    N+1. This helps the extractor see claim/evidence pairs that would otherwise
    be split across a hard chunk boundary.
    """
    if not full_text or not full_text.strip():
        return []

    sections = _split_by_sections(full_text, paradigm)
    chunks: list[TextChunk] = []

    for title, section_text, start, _end in sections:
        section_chunks = _split_oversized(title, section_text, start, max_chunk_chars, overlap_ratio=overlap_ratio)
        chunks.extend(section_chunks)

    # Fallback: if section-aware splitting produced nothing usable, use sliding window.
    if not chunks:
        chunks = _split_oversized(None, full_text, 0, max_chunk_chars, overlap_ratio=overlap_ratio)

    chunks = _merge_small_chunks(chunks, min_chunk_chars)

    # Re-index globally.
    return [
        TextChunk(
            index=i,
            title=c.title,
            text=c.text,
            start_char=c.start_char,
            end_char=c.end_char,
        )
        for i, c in enumerate(chunks)
    ]
