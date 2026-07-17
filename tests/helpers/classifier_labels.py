# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Load docs/v1/eval/classifier_labels.csv for ingest / classifier eval tests."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TypedDict

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER_LABELS_PATH = REPO_ROOT / "docs" / "v1" / "eval" / "classifier_labels.csv"

REQUIRED_COLUMNS = ("paper_id", "paradigm_gold", "title", "notes")
VALID_PARADIGMS = frozenset({"STEM", "HSS"})


class ClassifierLabelRow(TypedDict):
    paper_id: str
    paradigm_gold: str
    title: str
    notes: str


def load_classifier_labels(path: Path | None = None) -> list[ClassifierLabelRow]:
    """Parse classifier gold labels; raises if schema or paradigm values are invalid."""
    csv_path = path or CLASSIFIER_LABELS_PATH
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            msg = f"{csv_path}: missing header row"
            raise ValueError(msg)
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            msg = f"{csv_path}: missing columns {missing}"
            raise ValueError(msg)

        rows: list[ClassifierLabelRow] = []
        for line_number, raw in enumerate(reader, start=2):
            paper_id = (raw.get("paper_id") or "").strip()
            paradigm_gold = (raw.get("paradigm_gold") or "").strip()
            title = (raw.get("title") or "").strip()
            notes = (raw.get("notes") or "").strip()
            if not paper_id:
                msg = f"{csv_path}:{line_number}: empty paper_id"
                raise ValueError(msg)
            if paradigm_gold not in VALID_PARADIGMS:
                msg = f"{csv_path}:{line_number}: invalid paradigm_gold {paradigm_gold!r}"
                raise ValueError(msg)
            if not title:
                msg = f"{csv_path}:{line_number}: empty title for {paper_id}"
                raise ValueError(msg)
            rows.append(
                ClassifierLabelRow(
                    paper_id=paper_id,
                    paradigm_gold=paradigm_gold,
                    title=title,
                    notes=notes,
                ),
            )
    return rows


def labels_by_paper_id(path: Path | None = None) -> dict[str, ClassifierLabelRow]:
    rows = load_classifier_labels(path)
    mapping = {row["paper_id"]: row for row in rows}
    if len(mapping) != len(rows):
        msg = "duplicate paper_id in classifier_labels.csv"
        raise ValueError(msg)
    return mapping
