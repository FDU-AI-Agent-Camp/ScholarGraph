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
    assert len(large_window_chunks[0].text) >= len(default_chunks[0].text)
