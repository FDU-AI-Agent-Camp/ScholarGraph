"""PyMuPDF full-text extraction unit tests (BE-1)."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from backend.ingest.pdf import CLASSIFIER_HEAD_PAGE_LIMIT, extract_pdf_text, ingest_pdf
from tests.ingest.conftest import (
    write_empty_page_pdf,
    write_text_pdf,
    write_zero_page_pdf,
)


def test_extract_pdf_text_reads_all_pages(multi_page_pdf: Path) -> None:
    text = extract_pdf_text(multi_page_pdf)

    assert "Page one alpha content." in text
    assert "Page two beta content." in text
    assert "Page three gamma content." in text


def test_extract_pdf_text_max_pages_limits_to_prefix(multi_page_pdf: Path) -> None:
    limited = extract_pdf_text(multi_page_pdf, max_pages=2)
    full = extract_pdf_text(multi_page_pdf)

    assert "Page one alpha content." in limited
    assert "Page two beta content." in limited
    assert "Page three gamma content." not in limited
    assert len(limited) < len(full)


def test_extract_pdf_text_max_pages_beyond_doc_reads_all(multi_page_pdf: Path) -> None:
    text = extract_pdf_text(multi_page_pdf, max_pages=99)

    assert "Page three gamma content." in text


def test_extract_pdf_text_collapses_excessive_blank_lines(tmp_path: Path) -> None:
    pdf_path = write_text_pdf(
        tmp_path / "spacing.pdf",
        "Line A\n\n\n\n\nLine B",
    )

    text = extract_pdf_text(pdf_path)

    assert "Line A" in text
    assert "Line B" in text
    assert "\n\n\n" not in text


def test_extract_pdf_text_missing_file_reports_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError, match="PDF 不存在") as exc_info:
        extract_pdf_text(missing)

    assert str(missing.resolve()) in str(exc_info.value)


def test_extract_pdf_text_zero_pages_reports_error(tmp_path: Path) -> None:
    pdf_path = write_zero_page_pdf(tmp_path / "zero-page.pdf")

    with pytest.raises(ValueError, match="PDF 无页面") as exc_info:
        extract_pdf_text(pdf_path)

    assert str(pdf_path.resolve()) in str(exc_info.value)


def test_extract_pdf_text_blank_pages_reports_no_text(tmp_path: Path) -> None:
    pdf_path = write_empty_page_pdf(tmp_path / "blank.pdf")

    with pytest.raises(ValueError, match="PDF 未提取到文本") as exc_info:
        extract_pdf_text(pdf_path)

    assert str(pdf_path.resolve()) in str(exc_info.value)


def test_extract_pdf_text_corrupt_bytes_raises(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not-a-valid-pdf")

    with pytest.raises((RuntimeError, ValueError, fitz.FileDataError)):
        extract_pdf_text(corrupt)


async def test_ingest_pdf_full_text_longer_than_classifier_head(tmp_path: Path) -> None:
    pages = [f"Head page {index} with introductory material." for index in range(CLASSIFIER_HEAD_PAGE_LIMIT)]
    pages.extend([f"Tail page {index} with appendix-only content." for index in range(5)])
    pdf_path = write_text_pdf(tmp_path / "long.pdf", *pages)

    result = await ingest_pdf(pdf_path, paper_id="long-doc")

    assert result["paper_id"] == "long-doc"
    assert "Tail page 0" in result["full_text"]
    assert result["classifier_input"].strip()
    assert len(result["full_text"]) > len(result["classifier_input"])
