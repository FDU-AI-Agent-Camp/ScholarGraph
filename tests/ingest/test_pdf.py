# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""PDF ingest unit tests (BE-1). Corpus smoke见 test_corpus_smoke.py。"""

from pathlib import Path

import pytest
from backend.ingest.pdf import extract_pdf_text, resolve_paper_id


def test_resolve_paper_id_prefers_argument() -> None:
    assert resolve_paper_id(Path("data/corpus/stem-001.pdf"), "custom-id") == "custom-id"


def test_resolve_paper_id_falls_back_to_stem() -> None:
    assert resolve_paper_id(Path("data/corpus/stem-001.pdf"), None) == "stem-001"


def test_extract_pdf_text_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError, match="PDF 不存在"):
        extract_pdf_text(missing)
