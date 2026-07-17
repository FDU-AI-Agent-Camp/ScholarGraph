# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for page_start/page_end propagation from ingest to chunks."""

from __future__ import annotations

import tempfile
from pathlib import Path

import fitz
import pytest
from backend.ingest.pdf import extract_pdf_text_with_page_breaks, ingest_pdf
from backend.rag.chunking import chunk_text


def _make_two_page_pdf(path: Path) -> None:
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Page one content starts here.")
        page = document.new_page()
        page.insert_text((72, 72), "Page two content starts here.")
        document.save(path)


@pytest.mark.asyncio
async def test_ingest_pdf_provides_page_break_offsets() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "two_pages.pdf"
        _make_two_page_pdf(pdf_path)

        result = await ingest_pdf(pdf_path, paper_id="paper-1")

        assert "page_break_offsets" in result
        offsets = result["page_break_offsets"]
        assert len(offsets) == 2
        assert offsets[0] < offsets[1]
        full_text = result["full_text"]
        assert full_text


@pytest.mark.asyncio
async def test_chunk_text_uses_page_break_offsets_from_ingest() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "two_pages.pdf"
        _make_two_page_pdf(pdf_path)

        full_text, page_break_offsets = extract_pdf_text_with_page_breaks(pdf_path)
        chunks = chunk_text(
            "paper-1",
            full_text,
            chunk_size_chars=200,
            min_chunk_chars=1,
            page_break_offsets=page_break_offsets,
        )

        assert chunks
        for chunk in chunks:
            assert chunk.page_start is not None
            assert chunk.page_end is not None
            assert 1 <= chunk.page_start <= chunk.page_end <= 2


def test_page_resolver_handles_empty_offsets() -> None:
    chunks = chunk_text("paper-empty", "Some text without page offsets.", min_chunk_chars=1)
    assert chunks[0].page_start is None
    assert chunks[0].page_end is None


@pytest.mark.parametrize(
    ("offsets", "expected_start", "expected_end"),
    [
        ([5], 1, 1),  # boundary at text length; chunk ends at offset 4, still page 1
        ([100], 1, 1),  # boundary after the text
    ],
)
def test_page_resolver_edge_cases(
    offsets: list[int],
    expected_start: int,
    expected_end: int,
) -> None:
    chunks = chunk_text(
        "paper-edge",
        "Hello",
        min_chunk_chars=1,
        page_break_offsets=offsets,
    )
    assert len(chunks) == 1
    assert chunks[0].page_start == expected_start
    assert chunks[0].page_end == expected_end
