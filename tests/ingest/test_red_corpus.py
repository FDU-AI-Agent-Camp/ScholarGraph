# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
红灯语料测试（BE-1 ingest）

运行：uv run pytest -m red tests/ingest/test_red_corpus.py -rx
默认 CI：uv run pytest -m "not red"
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.ingest.pdf import ingest_pdf
from tests.helpers.classifier_labels import labels_by_paper_id
from tests.ingest.conftest import CORPUS_HSS, CORPUS_HSS_LONG, CORPUS_PAPER_IDS, CORPUS_STEM

CORPUS_CASES = (
    (CORPUS_STEM, "stem-001"),
    (CORPUS_HSS, "hss-001"),
    (CORPUS_HSS_LONG, "hss-002"),
)

CORPUS_STRUCTURE_MARKERS = {
    "stem-001": ("Title:", "Abstract:"),
    "hss-001": ("Title:", "Abstract:", "Keywords:", "夏尔巴"),
    "hss-002": ("Title:", "Abstract:", "Keywords:", "电影"),
}


@pytest.mark.red
@pytest.mark.parametrize(("pdf_path", "paper_id"), CORPUS_CASES, ids=CORPUS_PAPER_IDS)
async def test_ingest_pdf_corpus_full_text_non_empty(pdf_path: Path, paper_id: str) -> None:
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    result = await ingest_pdf(pdf_path, paper_id=paper_id)

    assert result["paper_id"] == paper_id
    assert len(result["full_text"].strip()) >= 100
    assert len(result["classifier_input"].strip()) >= 50
    assert len(result["classifier_input"]) <= len(result["full_text"])


@pytest.mark.red
@pytest.mark.parametrize(
    ("pdf_path", "paper_id"),
    CORPUS_CASES,
    ids=CORPUS_PAPER_IDS,
)
async def test_ingest_pdf_corpus_classifier_input_structure(
    pdf_path: Path,
    paper_id: str,
) -> None:
    if not pdf_path.is_file():
        pytest.skip(f"微语料 PDF 未就位: {pdf_path}")

    snippet = (await ingest_pdf(pdf_path, paper_id=paper_id))["classifier_input"]
    label = labels_by_paper_id()[paper_id]
    assert label["paradigm_gold"] in ("STEM", "HSS")

    for marker in CORPUS_STRUCTURE_MARKERS[paper_id]:
        assert marker in snippet, f"{paper_id}: missing {marker!r} in classifier_input"


@pytest.mark.red
async def test_ingest_pdf_missing_corpus_reports_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "stem-001.pdf"

    with pytest.raises(FileNotFoundError, match="PDF 不存在"):
        await ingest_pdf(missing, paper_id="stem-001")
