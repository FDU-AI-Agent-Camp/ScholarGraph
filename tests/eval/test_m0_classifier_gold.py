"""M0 eval — micro-corpus paradigm classification vs classifier_labels.csv gold.

Green: harness / CSV contract (CI default).
Red: end-to-end classify() vs gold (``pytest -m red`` until BE-2 delivers).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.agents.classifier import classify
from backend.ingest.pdf import ingest_pdf
from tests.helpers.classifier_labels import load_classifier_labels
from tests.ingest.conftest import CORPUS_HSS, CORPUS_HSS_LONG, CORPUS_STEM

CORPUS_BY_PAPER_ID = {
    "stem-001": CORPUS_STEM,
    "hss-001": CORPUS_HSS,
    "hss-002": CORPUS_HSS_LONG,
}


def test_m0_gold_labels_cover_three_corpus_papers() -> None:
    rows = load_classifier_labels()
    assert len(rows) == 3
    paradigms = {row["paradigm_gold"] for row in rows}
    assert paradigms == {"STEM", "HSS"}
    assert sum(1 for row in rows if row["paradigm_gold"] == "STEM") == 1
    assert sum(1 for row in rows if row["paradigm_gold"] == "HSS") == 2


@pytest.mark.red
@pytest.mark.parametrize(
    "paper_id",
    ["stem-001", "hss-001", "hss-002"],
)
@pytest.mark.xfail(strict=True, reason="BE-2: classify() 尚未实现 — M0 3/3 待交付")
async def test_m0_classify_matches_gold_label(paper_id: str) -> None:
    """A-07 / M0: classify(classifier_input) paradigm == paradigm_gold."""
    pdf_path: Path = CORPUS_BY_PAPER_ID[paper_id]
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    gold = next(row for row in load_classifier_labels() if row["paper_id"] == paper_id)
    snippet = (await ingest_pdf(pdf_path, paper_id=paper_id))["classifier_input"]
    result = await classify(snippet)

    assert result.paradigm.value == gold["paradigm_gold"]
    assert 0.0 <= result.confidence <= 1.0
    assert result.reason.strip()


def test_m0_classifier_labels_rejects_invalid_paradigm(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "paper_id,paradigm_gold,title,notes\nx-001,INVALID,Title,note\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid paradigm_gold"):
        load_classifier_labels(bad_csv)
