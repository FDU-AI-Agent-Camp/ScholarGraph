"""PDF parsing (BE-1)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import NotRequired, TypedDict

import fitz

from backend.ingest.snippets import build_classifier_input, normalize_whitespace

# Large theses may place 摘要 after cover pages; scan enough front matter only for classification.
CLASSIFIER_HEAD_PAGE_LIMIT = 25


class IngestResult(TypedDict):
    paper_id: str
    full_text: str
    classifier_input: str
    page_break_offsets: NotRequired[list[int]]


def resolve_paper_id(file_path: Path, paper_id: str | None) -> str:
    """Derive paper_id from argument or PDF stem."""
    if paper_id is not None and paper_id.strip():
        return paper_id.strip()
    return file_path.stem


def extract_pdf_text(file_path: Path, *, max_pages: int | None = None) -> str:
    """
    Extract plain text from a PDF using PyMuPDF.

    Args:
        file_path: Path to an existing PDF file.
        max_pages: When set, only read the first N pages (for classifier head extraction).

    Raises:
        FileNotFoundError: PDF path does not exist.
        ValueError: PDF has no extractable text.
    """
    return extract_pdf_text_with_page_breaks(file_path, max_pages=max_pages)[0]


def extract_pdf_text_with_page_breaks(
    file_path: Path,
    *,
    max_pages: int | None = None,
) -> tuple[str, list[int]]:
    """
    Extract plain text from a PDF and record normalized page-boundary offsets.

    Returns:
        A tuple of (normalized full text, page-break offsets). Each offset is the
        character position immediately after the end of the corresponding page in
        the normalized text. Offsets are 1-based page indices: page N occupies
        the half-open interval [offset_{N-1}, offset_N) where offset_0 is 0.

    Raises:
        FileNotFoundError: PDF path does not exist.
        ValueError: PDF has no extractable text.
    """
    resolved = file_path.resolve()
    if not resolved.is_file():
        msg = f"PDF 不存在: {resolved}"
        raise FileNotFoundError(msg)

    with fitz.open(resolved) as document:
        page_count = document.page_count
        if page_count == 0:
            msg = f"PDF 无页面: {resolved}"
            raise ValueError(msg)

        limit = page_count if max_pages is None else min(page_count, max_pages)
        page_texts: list[str] = []
        for page_index in range(limit):
            raw_text = document.load_page(page_index).get_text()
            page_texts.append(raw_text if isinstance(raw_text, str) else str(raw_text))

    normalized_page_texts = [normalize_whitespace(text) for text in page_texts]
    combined = normalize_whitespace("\n\n".join(normalized_page_texts))
    if not combined:
        msg = f"PDF 未提取到文本: {resolved}"
        raise ValueError(msg)

    page_break_offsets: list[int] = []
    cumulative = 0
    for page_text in normalized_page_texts:
        # normalize_whitespace joins pages with a blank line when we combine them,
        # so each boundary is offset by the separator length (2 newlines = 2 chars)
        # except for the first page.
        if page_break_offsets:
            cumulative += 2
        cumulative += len(page_text)
        page_break_offsets.append(cumulative)

    return combined, page_break_offsets


async def ingest_pdf(file_path: Path, paper_id: str | None = None) -> IngestResult:
    """Parse PDF and return full text plus classifier input snippet."""
    resolved = file_path.resolve()
    resolved_id = resolve_paper_id(resolved, paper_id)

    full_text, page_break_offsets = await asyncio.to_thread(extract_pdf_text_with_page_breaks, resolved)
    head_text = await asyncio.to_thread(
        extract_pdf_text,
        resolved,
        max_pages=CLASSIFIER_HEAD_PAGE_LIMIT,
    )
    classifier_input = build_classifier_input(head_text, full_text=full_text)
    if not classifier_input.strip():
        classifier_input = build_classifier_input(full_text[:50_000], full_text=full_text)

    return IngestResult(
        paper_id=resolved_id,
        full_text=full_text,
        classifier_input=classifier_input,
        page_break_offsets=page_break_offsets,
    )
