"""Corpus smoke tests: gold labels ↔ local PDFs ↔ ingest output (BE-1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.ingest.pdf import extract_pdf_text, ingest_pdf
from tests.helpers.classifier_labels import labels_by_paper_id
from tests.ingest.conftest import CORPUS_DIR, CORPUS_PAPER_IDS

# Short phrases from classifier_labels title / notes used to sanity-check extraction.
TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "stem-001": ("atomic embeddings", "machine learning", "crystal"),
    "hss-001": ("夏尔巴", "父系"),
    "hss-002": ("电影", "政治传播"),
}


def _corpus_pdf(paper_id: str) -> Path:
    return CORPUS_DIR / f"{paper_id}.pdf"


def test_corpus_directory_exists() -> None:
    assert CORPUS_DIR.is_dir()


@pytest.mark.parametrize("paper_id", CORPUS_PAPER_IDS)
def test_corpus_pdf_present_or_skip(paper_id: str) -> None:
    pdf_path = _corpus_pdf(paper_id)
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")
    assert pdf_path.stat().st_size > 0


@pytest.mark.parametrize("paper_id", CORPUS_PAPER_IDS)
async def test_corpus_ingest_matches_gold_label_metadata(paper_id: str) -> None:
    pdf_path = _corpus_pdf(paper_id)
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    label = labels_by_paper_id()[paper_id]
    result = await ingest_pdf(pdf_path, paper_id=paper_id)

    assert result["paper_id"] == paper_id
    assert result["full_text"].strip()
    assert result["classifier_input"].strip()
    assert len(result["classifier_input"]) <= len(result["full_text"])

    full_lower = result["full_text"].lower()
    hints = TITLE_HINTS[paper_id]
    assert any(
        hint.lower() in full_lower if hint.isascii() else hint in result["full_text"]
        for hint in hints
    ), f"{paper_id}: full_text missing expected hints {hints} (title={label['title']!r})"


@pytest.mark.parametrize("paper_id", CORPUS_PAPER_IDS)
def test_corpus_extract_text_non_empty(paper_id: str) -> None:
    pdf_path = _corpus_pdf(paper_id)
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    text = extract_pdf_text(pdf_path)
    assert len(text) >= 100


@pytest.mark.parametrize(
    ("paper_id", "required_markers"),
    [
        ("stem-001", ("Title:", "Abstract:")),
        ("hss-001", ("Title:", "Abstract:", "Keywords:", "夏尔巴")),
        ("hss-002", ("Title:", "Abstract:", "Keywords:", "电影")),
    ],
)
async def test_corpus_classifier_input_structure(paper_id: str, required_markers: tuple[str, ...]) -> None:
    pdf_path = _corpus_pdf(paper_id)
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    snippet = (await ingest_pdf(pdf_path, paper_id=paper_id))["classifier_input"]
    for marker in required_markers:
        assert marker in snippet, f"{paper_id}: missing {marker!r}"
