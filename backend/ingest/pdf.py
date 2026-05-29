"""PDF parsing (BE-1)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TypedDict

import fitz

from backend.ingest.snippets import build_classifier_input, normalize_whitespace

# Large theses may place 摘要 after cover pages; scan enough front matter only for classification.
CLASSIFIER_HEAD_PAGE_LIMIT = 25


class IngestResult(TypedDict):
    paper_id: str
    full_text: str
    classifier_input: str


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
            page_texts.append(document.load_page(page_index).get_text())

    combined = normalize_whitespace("\n\n".join(page_texts))
    if not combined:
        msg = f"PDF 未提取到文本: {resolved}"
        raise ValueError(msg)
    return combined


async def ingest_pdf(file_path: Path, paper_id: str | None = None) -> IngestResult:
    """Parse PDF and return full text plus classifier input snippet."""
    resolved = file_path.resolve()
    resolved_id = resolve_paper_id(resolved, paper_id)

    full_text = await asyncio.to_thread(extract_pdf_text, resolved)
    head_text = await asyncio.to_thread(
        extract_pdf_text,
        resolved,
        max_pages=CLASSIFIER_HEAD_PAGE_LIMIT,
    )
    classifier_input = build_classifier_input(head_text)
    if not classifier_input.strip():
        classifier_input = build_classifier_input(full_text[:50_000])

    return IngestResult(
        paper_id=resolved_id,
        full_text=full_text,
        classifier_input=classifier_input,
    )
