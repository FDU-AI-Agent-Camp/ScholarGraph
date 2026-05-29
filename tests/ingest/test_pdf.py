"""PDF ingest tests (BE-1)."""

from pathlib import Path

import pytest
from backend.ingest.pdf import extract_pdf_text, ingest_pdf, resolve_paper_id

CORPUS_DIR = Path("data/corpus")
CORPUS_STEM = CORPUS_DIR / "stem-001.pdf"
CORPUS_HSS = CORPUS_DIR / "hss-001.pdf"
CORPUS_HSS_LONG = CORPUS_DIR / "hss-002.pdf"


def test_resolve_paper_id_prefers_argument() -> None:
    assert resolve_paper_id(Path("data/corpus/stem-001.pdf"), "custom-id") == "custom-id"


def test_resolve_paper_id_falls_back_to_stem() -> None:
    assert resolve_paper_id(Path("data/corpus/stem-001.pdf"), None) == "stem-001"


def test_extract_pdf_text_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError, match="PDF 不存在"):
        extract_pdf_text(missing)


@pytest.mark.parametrize(
    ("pdf_path", "paper_id"),
    [
        (CORPUS_STEM, "stem-001"),
        (CORPUS_HSS, "hss-001"),
        (CORPUS_HSS_LONG, "hss-002"),
    ],
)
async def test_ingest_pdf_corpus_smoke(pdf_path: Path, paper_id: str) -> None:
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    result = await ingest_pdf(pdf_path, paper_id=paper_id)

    assert result["paper_id"] == paper_id
    assert result["full_text"].strip()
    assert result["classifier_input"].strip()
    assert len(result["classifier_input"]) <= len(result["full_text"])


@pytest.mark.parametrize(
    ("pdf_path", "expected_markers"),
    [
        (CORPUS_STEM, ("Abstract:", "machine learning", "Introduction:")),
        (CORPUS_HSS, ("Abstract:", "夏尔巴", "Keywords:", "Introduction:")),
        (CORPUS_HSS_LONG, ("Abstract:", "电影", "Keywords:")),
    ],
)
async def test_classifier_input_contains_expected_sections(
    pdf_path: Path,
    expected_markers: tuple[str, ...],
) -> None:
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    result = await ingest_pdf(pdf_path)
    snippet = result["classifier_input"]
    for marker in expected_markers:
        assert marker in snippet, f"missing {marker!r} in classifier_input for {pdf_path.name}"
