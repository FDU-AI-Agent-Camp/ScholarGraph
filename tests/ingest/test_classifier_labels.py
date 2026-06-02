"""Unit tests for docs/v1/eval/classifier_labels.csv (P1 eval gold labels)."""

from __future__ import annotations

import csv

import pytest
from tests.helpers.classifier_labels import (
    CLASSIFIER_LABELS_PATH,
    REQUIRED_COLUMNS,
    labels_by_paper_id,
    load_classifier_labels,
)
from tests.ingest.conftest import CORPUS_DIR, CORPUS_PAPER_IDS


def test_classifier_labels_file_exists() -> None:
    assert CLASSIFIER_LABELS_PATH.is_file()


def test_classifier_labels_schema_and_paradigm_counts() -> None:
    rows = load_classifier_labels()
    assert len(rows) == 3

    paradigms = {row["paradigm_gold"] for row in rows}
    assert paradigms == {"STEM", "HSS"}
    assert sum(1 for row in rows if row["paradigm_gold"] == "STEM") == 1
    assert sum(1 for row in rows if row["paradigm_gold"] == "HSS") == 2


def test_classifier_labels_paper_ids_match_corpus_constants() -> None:
    labels = labels_by_paper_id()
    assert tuple(sorted(labels)) == tuple(sorted(CORPUS_PAPER_IDS))


def test_classifier_labels_each_row_has_title_and_notes() -> None:
    for row in load_classifier_labels():
        assert row["title"].strip()
        assert row["notes"].strip()


def test_classifier_labels_utf8_header_exact() -> None:
    with CLASSIFIER_LABELS_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
    assert header == list(REQUIRED_COLUMNS)


@pytest.mark.parametrize("paper_id", CORPUS_PAPER_IDS)
def test_classifier_labels_pdf_path_follows_convention(paper_id: str) -> None:
    expected = CORPUS_DIR / f"{paper_id}.pdf"
    labels = labels_by_paper_id()
    assert labels[paper_id]["paper_id"] == paper_id
    assert expected.name == f"{paper_id}.pdf"
