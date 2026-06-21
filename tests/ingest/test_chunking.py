"""Tests for backend.ingest.chunking."""

from __future__ import annotations

from backend.ingest.chunking import chunk_text
from backend.schemas.paradigm import Paradigm


def _stem_text(section_sizes: dict[str, int]) -> str:
    parts = []
    for title, sentences in section_sizes.items():
        parts.append(f"{title}\n\n")
        parts.append(". ".join(f"Sentence {i} in {title}" for i in range(sentences)) + ".")
    return "\n\n".join(parts)


class TestChunkText:
    def test_stem_section_aware_splitting(self) -> None:
        text = _stem_text({"Introduction": 30, "Methods": 30, "Results": 30, "Conclusion": 30})
        chunks = chunk_text(text, Paradigm.STEM, max_chunk_chars=1000, min_chunk_chars=0)
        titles = [c.title for c in chunks]
        assert "Introduction" in titles
        assert "Methods" in titles
        assert "Results" in titles
        assert "Conclusion" in titles
        assert all(len(c.text) <= 1000 for c in chunks)

    def test_hss_section_aware_splitting(self) -> None:
        text = (
            "Introduction\n\n" + ("We study X. " * 100) + "\n\n"
            "Theoretical Framework\n\n" + ("Theory Y informs our work. " * 100) + "\n\n"
            "Analysis\n\n" + ("We analyze the data. " * 100) + "\n\n"
            "Conclusion\n\n" + ("In conclusion. " * 100)
        )
        chunks = chunk_text(text, Paradigm.HSS, max_chunk_chars=1000, min_chunk_chars=0)
        titles = [c.title for c in chunks]
        assert "Theoretical Framework" in titles
        assert "Analysis" in titles
        assert "Conclusion" in titles

    def test_oversized_section_split_by_paragraph(self) -> None:
        paragraphs = [f"Paragraph {i}. " * 50 for i in range(10)]
        text = "Methods\n\n" + "\n\n".join(paragraphs)
        chunks = chunk_text(text, Paradigm.STEM, max_chunk_chars=1000, min_chunk_chars=0)
        assert len(chunks) > 1
        assert all(c.title == "Methods" for c in chunks)
        assert all(len(c.text) <= 1000 for c in chunks)

    def test_no_section_headers_falls_back_to_sliding_window(self) -> None:
        text = "This is a long paragraph. " * 500
        chunks = chunk_text(text, Paradigm.STEM, max_chunk_chars=1000, min_chunk_chars=0)
        assert len(chunks) > 1
        assert all(c.title is None for c in chunks)
        assert all(len(c.text) <= 1000 for c in chunks)

    def test_tiny_chunks_merged_with_neighbors(self) -> None:
        text = "Introduction\n\nShort.\n\nMethods\n\n" + ("We use method X. " * 200) + "\n\nResults\n\nOk."
        chunks = chunk_text(text, Paradigm.STEM, max_chunk_chars=2000)
        # The tiny "Short" and "Ok" chunks should be merged into neighbors.
        assert len(chunks) <= 2
        assert all(len(c.text) >= 500 for c in chunks)

    def test_empty_text_returns_empty(self) -> None:
        assert chunk_text("", Paradigm.HSS) == []
        assert chunk_text("   ", Paradigm.STEM) == []

    def test_chunk_indices_are_sequential(self) -> None:
        text = "Introduction\n\n" + ("Hello world. " * 200)
        chunks = chunk_text(text, Paradigm.STEM, max_chunk_chars=500, min_chunk_chars=0)
        assert [c.index for c in chunks] == list(range(len(chunks)))
