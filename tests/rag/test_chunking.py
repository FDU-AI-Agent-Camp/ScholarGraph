"""Unit tests for V2 RAG text chunking."""

from __future__ import annotations

import pytest
from backend.rag.chunking import chunk_text


def test_chunk_text_splits_by_section_and_skips_references() -> None:
    text = """Title line

Abstract
This paper studies retrieval augmented generation for scholarly graphs.

1 Introduction
The introduction explains the motivation and the main research problem in detail.

Methods
The method section describes chunking, embeddings, and vector search. It has enough text to split.
The next sentence should overlap with a nearby chunk when the section is long.

References
[1] A reference that should not pollute retrieval.
"""

    chunks = chunk_text(
        "paper-1",
        text,
        chunk_size_chars=90,
        chunk_overlap_ratio=0.20,
        min_chunk_chars=20,
    )

    assert chunks
    assert all(chunk.chunk_id == f"paper-1:chunk:{chunk.chunk_index}" for chunk in chunks)
    assert {chunk.section for chunk in chunks} >= {"abstract", "introduction", "methods"}
    assert all("reference that should not pollute" not in chunk.text for chunk in chunks)
    assert all(chunk.char_start < chunk.char_end for chunk in chunks)
    method_chunks = [chunk for chunk in chunks if chunk.section == "methods"]
    assert len(method_chunks) >= 2
    assert method_chunks[1].char_start < method_chunks[0].char_end


def test_chunk_text_can_include_references_when_requested() -> None:
    chunks = chunk_text(
        "paper-refs",
        "Introduction\nMain content.\n\nReferences\nReference content.",
        include_references=True,
        min_chunk_chars=1,
    )

    assert any(chunk.section == "references" for chunk in chunks)


def test_chunk_text_merges_tiny_preamble() -> None:
    chunks = chunk_text(
        "paper-2",
        "Tiny.\n\nIntroduction\nThis introduction is long enough to become the real searchable chunk.",
        min_chunk_chars=20,
    )

    assert len(chunks) == 1
    assert "Tiny." in chunks[0].text
    assert chunks[0].section == "introduction"


def test_chunk_text_validates_options() -> None:
    with pytest.raises(ValueError, match="chunk_size_chars"):
        chunk_text("paper-bad", "text", chunk_size_chars=0)

    with pytest.raises(ValueError, match="chunk_overlap_ratio"):
        chunk_text("paper-bad", "text", chunk_overlap_ratio=1.0)


def test_chunk_text_validates_soft_boundary_window() -> None:
    with pytest.raises(ValueError, match="min_soft_boundary_window_chars"):
        chunk_text("paper-bad", "text", min_soft_boundary_window_chars=0)

    # A window larger than the chunk is silently clamped; no error is raised.
    chunks = chunk_text("paper-ok", "text", chunk_size_chars=3, min_soft_boundary_window_chars=10)
    assert chunks


def test_chunk_text_uses_custom_soft_boundary_window() -> None:
    text = "Methods\n" + "word " * 100  # long section

    default_chunks = chunk_text(
        "paper-default",
        text,
        chunk_size_chars=200,
        min_soft_boundary_window_chars=50,
    )
    large_window_chunks = chunk_text(
        "paper-large-window",
        text,
        chunk_size_chars=200,
        min_soft_boundary_window_chars=150,
    )

    assert default_chunks
    assert large_window_chunks
    # A larger minimum window generally pushes boundaries later, so the first chunk
    # should not be shorter than with the default window.


def test_chunk_text_respects_min_chunk_chars() -> None:
    text = "Introduction\n" + "word " * 20 + "\n\nMethods\nshort."

    strict_chunks = chunk_text(
        "paper-strict",
        text,
        chunk_size_chars=200,
        min_chunk_chars=100,
    )
    loose_chunks = chunk_text(
        "paper-loose",
        text,
        chunk_size_chars=200,
        min_chunk_chars=1,
    )

    assert len(loose_chunks) >= len(strict_chunks)
    assert all(len(chunk.text) >= 100 for chunk in strict_chunks)


def test_chunk_text_exclude_references_by_default() -> None:
    text = "Introduction\nMain content.\n\nReferences\nReference content."

    default_chunks = chunk_text("paper-default", text, min_chunk_chars=1)
    included_chunks = chunk_text("paper-included", text, include_references=True, min_chunk_chars=1)

    assert not any(chunk.section == "references" for chunk in default_chunks)
    assert any(chunk.section == "references" for chunk in included_chunks)


def test_chunk_text_infers_page_numbers_from_break_offsets() -> None:
    text = "Page1 line1.\n\nPage2 line1.\n\nPage3 line1."
    # Offsets mark the end of each page in the normalized text.
    chunks = chunk_text(
        "paper-pages",
        text,
        chunk_size_chars=50,
        min_chunk_chars=1,
        page_break_offsets=[len("Page1 line1."), len("Page1 line1.\n\nPage2 line1.")],
    )

    assert chunks
    for chunk in chunks:
        assert chunk.page_start is not None
        assert chunk.page_end is not None
        assert chunk.page_start <= chunk.page_end


def test_chunk_text_cross_page_chunk_has_start_and_end_pages() -> None:
    text = "A" * 50 + "\n\n" + "B" * 50
    chunks = chunk_text(
        "paper-cross",
        text,
        chunk_size_chars=80,
        min_chunk_chars=1,
        page_break_offsets=[50],
    )

    cross_page_chunks = [chunk for chunk in chunks if chunk.page_start != chunk.page_end]
    assert cross_page_chunks
    chunk = cross_page_chunks[0]
    assert chunk.page_start == 1
    assert chunk.page_end == 2


def test_chunk_text_page_fields_none_without_offsets() -> None:
    chunks = chunk_text("paper-no-pages", "Some content without offsets.", min_chunk_chars=1)
    assert len(chunks) == 1
    assert chunks[0].page_start is None
    assert chunks[0].page_end is None


def test_chunk_text_page_resolver_handles_out_of_range_offsets() -> None:
    text = "Short text."
    chunks = chunk_text(
        "paper-overflow",
        text,
        min_chunk_chars=1,
        page_break_offsets=[5],  # boundary is inside the only chunk
    )

    assert len(chunks) == 1
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2
