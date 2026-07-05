"""Section-aware text chunking for V2 RAG indexing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.rag.models import PaperChunk

DEFAULT_CHUNK_SIZE_CHARS = 1500
DEFAULT_CHUNK_OVERLAP_RATIO = 0.20
DEFAULT_MIN_CHUNK_CHARS = 200
DEFAULT_MIN_SOFT_BOUNDARY_WINDOW_CHARS = 200
DEFAULT_SOURCE = "pymupdf"

SECTION_ALIASES: dict[str, str] = {
    "abstract": "abstract",
    "summary": "abstract",
    "introduction": "introduction",
    "related work": "related_work",
    "background": "background",
    "preliminaries": "preliminaries",
    "method": "methods",
    "methods": "methods",
    "methodology": "methods",
    "model": "methods",
    "architecture": "methods",
    "experiment": "experiments",
    "experiments": "experiments",
    "experimental setup": "experiments",
    "evaluation": "results",
    "results": "results",
    "findings": "results",
    "discussion": "discussion",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "appendix": "appendix",
    "references": "references",
    "bibliography": "references",
    "works cited": "references",
}
REFERENCE_SECTIONS = frozenset({"references"})
_SECTION_PATTERN = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+|[IVXivx]+\.?\s+)?("
    + "|".join(re.escape(title) for title in sorted(SECTION_ALIASES, key=len, reverse=True))
    + r")\s*(?:[:.\-])?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class _TextSlice:
    section: str | None
    start: int
    end: int


def chunk_text(
    paper_id: str,
    full_text: str,
    *,
    source: str = DEFAULT_SOURCE,
    chunk_size_chars: int = DEFAULT_CHUNK_SIZE_CHARS,
    chunk_overlap_ratio: float = DEFAULT_CHUNK_OVERLAP_RATIO,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    min_soft_boundary_window_chars: int = DEFAULT_MIN_SOFT_BOUNDARY_WINDOW_CHARS,
    include_references: bool = False,
) -> list[PaperChunk]:
    """Split paper text into deterministic, section-aware RAG chunks."""

    normalized_text = _normalize_text(full_text)
    if not normalized_text.strip():
        return []

    _validate_chunk_options(chunk_size_chars, chunk_overlap_ratio, min_chunk_chars)
    _validate_soft_boundary_window(min_soft_boundary_window_chars, chunk_size_chars)
    sections = _section_slices(normalized_text)
    raw_chunks: list[_TextSlice] = []
    for section_slice in sections:
        if section_slice.section in REFERENCE_SECTIONS and not include_references:
            continue
        raw_chunks.extend(
            _split_slice(
                normalized_text,
                section_slice,
                chunk_size_chars=chunk_size_chars,
                chunk_overlap_ratio=chunk_overlap_ratio,
                min_soft_boundary_window_chars=min_soft_boundary_window_chars,
            )
        )

    merged_chunks = _merge_tiny_slices(normalized_text, raw_chunks, min_chunk_chars)
    return [
        PaperChunk(
            chunk_id=_chunk_id(paper_id, index),
            paper_id=paper_id,
            text=normalized_text[text_slice.start : text_slice.end].strip(),
            page_start=None,
            page_end=None,
            section=text_slice.section,
            chunk_index=index,
            source=source,
            char_start=text_slice.start,
            char_end=text_slice.end,
        )
        for index, text_slice in enumerate(merged_chunks)
        if normalized_text[text_slice.start : text_slice.end].strip()
    ]


def _normalize_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def _validate_chunk_options(chunk_size_chars: int, chunk_overlap_ratio: float, min_chunk_chars: int) -> None:
    if chunk_size_chars <= 0:
        raise ValueError("chunk_size_chars must be positive.")
    if not 0 <= chunk_overlap_ratio < 1:
        raise ValueError("chunk_overlap_ratio must be in [0, 1).")
    if min_chunk_chars < 0:
        raise ValueError("min_chunk_chars must be non-negative.")


def _validate_soft_boundary_window(min_soft_boundary_window_chars: int, chunk_size_chars: int) -> None:
    del chunk_size_chars  # validated implicitly by _find_soft_boundary clamping
    if min_soft_boundary_window_chars <= 0:
        raise ValueError("min_soft_boundary_window_chars must be positive.")


def _chunk_id(paper_id: str, chunk_index: int) -> str:
    return f"{paper_id}:chunk:{chunk_index}"


def _section_slices(text: str) -> list[_TextSlice]:
    matches = list(_SECTION_PATTERN.finditer(text))
    if not matches:
        start, end = _trim_bounds(text, 0, len(text))
        return [_TextSlice(section=None, start=start, end=end)] if start < end else []

    slices: list[_TextSlice] = []
    first = matches[0]
    preamble_start, preamble_end = _trim_bounds(text, 0, first.start())
    if preamble_start < preamble_end:
        slices.append(_TextSlice(section=None, start=preamble_start, end=preamble_end))

    for index, match in enumerate(matches):
        section_name = _canonical_section(match.group(1))
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        start, end = _trim_bounds(text, body_start, body_end)
        if start < end:
            slices.append(_TextSlice(section=section_name, start=start, end=end))
    return slices


def _canonical_section(raw_title: str) -> str:
    normalized = re.sub(r"\s+", " ", raw_title.strip().lower())
    return SECTION_ALIASES[normalized]


def _trim_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split_slice(
    text: str,
    text_slice: _TextSlice,
    *,
    chunk_size_chars: int,
    chunk_overlap_ratio: float,
    min_soft_boundary_window_chars: int,
) -> list[_TextSlice]:
    if text_slice.end - text_slice.start <= chunk_size_chars:
        return [text_slice]

    overlap_chars = int(chunk_size_chars * chunk_overlap_ratio)
    min_step = max(1, chunk_size_chars - overlap_chars)
    chunks: list[_TextSlice] = []
    start = text_slice.start
    while start < text_slice.end:
        target_end = min(start + chunk_size_chars, text_slice.end)
        end = _find_soft_boundary(
            text,
            start,
            target_end,
            text_slice.end,
            min_soft_boundary_window_chars=min_soft_boundary_window_chars,
        )
        trimmed_start, trimmed_end = _trim_bounds(text, start, end)
        if trimmed_start < trimmed_end:
            chunks.append(_TextSlice(section=text_slice.section, start=trimmed_start, end=trimmed_end))
        if end >= text_slice.end:
            break
        start = max(end - overlap_chars, start + min_step)
    return chunks


def _find_soft_boundary(
    text: str,
    start: int,
    target_end: int,
    hard_end: int,
    *,
    min_soft_boundary_window_chars: int,
) -> int:
    if target_end >= hard_end:
        return hard_end

    min_end = min(start + max(min_soft_boundary_window_chars, (target_end - start) // 2), target_end)
    boundary_chars = ("\n\n", ". ", "\u3002", "? ", "! ", "\uff1f", "\uff01", "\n")
    window = text[min_end:target_end]
    for marker in boundary_chars:
        position = window.rfind(marker)
        if position != -1:
            return min_end + position + len(marker)
    return target_end


def _merge_tiny_slices(text: str, chunks: list[_TextSlice], min_chunk_chars: int) -> list[_TextSlice]:
    if len(chunks) <= 1 or min_chunk_chars <= 0:
        return chunks

    merged: list[_TextSlice] = []
    pending: _TextSlice | None = None
    for chunk in chunks:
        active = _join_slices(text, pending, chunk) if pending is not None else chunk
        pending = None
        if active.end - active.start < min_chunk_chars:
            if merged:
                merged[-1] = _join_slices(text, merged[-1], active)
            else:
                pending = active
            continue
        merged.append(active)

    if pending is not None:
        if merged:
            merged[-1] = _join_slices(text, merged[-1], pending)
        else:
            merged.append(pending)
    return merged


def _join_slices(text: str, first: _TextSlice | None, second: _TextSlice) -> _TextSlice:
    if first is None:
        return second
    start, end = _trim_bounds(text, first.start, second.end)
    return _TextSlice(section=first.section or second.section, start=start, end=end)
