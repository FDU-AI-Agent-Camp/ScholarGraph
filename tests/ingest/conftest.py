"""Shared fixtures for ingest tests."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

CORPUS_DIR = Path("data/corpus")
CORPUS_STEM = CORPUS_DIR / "stem-001.pdf"
CORPUS_HSS = CORPUS_DIR / "hss-001.pdf"
CORPUS_HSS_LONG = CORPUS_DIR / "hss-002.pdf"
CORPUS_PAPER_IDS = ("stem-001", "hss-001", "hss-002")


def write_text_pdf(path: Path, *page_texts: str) -> Path:
    """Create a minimal PDF with extractable text on each page."""
    document = fitz.open()
    for page_text in page_texts:
        page = document.new_page()
        if page_text.strip():
            y = 72
            for line in page_text.splitlines():
                page.insert_text((72, y), line, fontsize=11)
                y += 14
    document.save(path)
    document.close()
    return path


def write_empty_page_pdf(path: Path, *, page_count: int = 1) -> Path:
    """Create a PDF whose pages contain no extractable text."""
    document = fitz.open()
    for _ in range(page_count):
        document.new_page()
    document.save(path)
    document.close()
    return path


def write_zero_page_pdf(path: Path) -> Path:
    """Write a minimal PDF shell; PyMuPDF cannot save zero-page documents."""
    path.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<< /Root 1 0 R /Size 1 >>\nstartxref\n9\n%%EOF\n")
    return path


def register_pending_paper(paper_id: str, *, title: str = "ingest test paper") -> None:
    """Register paper in PaperService so ingest_node can update status."""
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData
    from backend.services.paper_service import get_paper_service

    now = datetime.now(UTC)
    service = get_paper_service()
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title=title,
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    service._status[paper_id] = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PENDING,
        percent=0,
        stage=None,
        message="ingest test fixture",
        updated_at=now,
    )


@pytest.fixture
def structured_stem_pdf(tmp_path: Path) -> Path:
    """STEM-style PDF with explicit Abstract / Keywords / Introduction markers."""
    content = "\n".join(
        [
            "Transformer Model for Crystal Properties",
            "Jane Researcher, University of Test",
            "",
            "Abstract",
            "This paper presents a machine learning method for crystal property prediction.",
            "We evaluate accuracy on benchmark datasets with strong baselines.",
            "",
            "Keywords",
            "machine learning, materials science, crystals",
            "",
            "Introduction",
            "The development of deep learning has created new methods for materials science.",
            "Many graph neural network models have been proposed for property prediction.",
        ]
    )
    return write_text_pdf(tmp_path / "structured-stem.pdf", content)


@pytest.fixture
def multi_page_pdf(tmp_path: Path) -> Path:
    return write_text_pdf(
        tmp_path / "multi-page.pdf",
        "Page one alpha content.",
        "Page two beta content.",
        "Page three gamma content.",
    )


def _threshold_page_text(page_index: int) -> str:
    return f"Threshold test page {page_index} with extractable text content."


@pytest.fixture
def pdf_25_pages(tmp_path: Path) -> Path:
    """Exactly 25 pages — boundary for short-PDF MinerU route."""
    pages = [_threshold_page_text(index) for index in range(1, 26)]
    return write_text_pdf(tmp_path / "exactly-25-pages.pdf", *pages)


@pytest.fixture
def pdf_26_pages(tmp_path: Path) -> Path:
    """Exactly 26 pages — first page over short-PDF threshold (GROBID route)."""
    pages = [_threshold_page_text(index) for index in range(1, 27)]
    return write_text_pdf(tmp_path / "exactly-26-pages.pdf", *pages)
