"""Unit tests for QA answer Markdown sanitization."""

from __future__ import annotations

import pytest
from backend.graph.qa_text_sanitize import (
    QaTextSanitizer,
    sanitize_qa_answer_final,
    sanitize_qa_text_chunk,
)


class TestSanitizeQaTextChunk:
    def test_removes_empty_backtick_pair(self) -> None:
        assert sanitize_qa_text_chunk("问题``。") == "问题。"

    def test_strips_inline_code_with_meaningful_content(self) -> None:
        assert sanitize_qa_text_chunk("`RAG-Sequence`") == "RAG-Sequence"

    def test_strips_bold_markers(self) -> None:
        assert sanitize_qa_text_chunk("这是**重点**内容") == "这是重点内容"

    def test_strips_header_markers(self) -> None:
        assert sanitize_qa_text_chunk("## 标题\n正文") == "标题\n正文"

    def test_removes_excess_backticks(self) -> None:
        assert sanitize_qa_text_chunk("a````b") == "ab"

    def test_strips_bold_markers_across_complete_text(self) -> None:
        assert sanitize_qa_text_chunk("这是**重点**内容") == "这是重点内容"


class TestSanitizeQaAnswerFinal:
    def test_removes_orphan_backticks(self) -> None:
        assert sanitize_qa_answer_final("问题`。") == "问题。"

    def test_collapses_trailing_backtick_runs(self) -> None:
        assert sanitize_qa_answer_final("方案 `` 完成") == "方案 完成"


class TestQaTextSanitizerStreaming:
    def test_cross_chunk_backtick_truncation_does_not_leak_orphan_marker(self) -> None:
        sanitizer = QaTextSanitizer()
        parts = [
            sanitizer.feed("问题"),
            sanitizer.feed("`"),
            sanitizer.feed("`。"),
            sanitizer.flush(),
        ]
        assert "".join(part for part in parts if part) == "问题。"

    def test_feed_empty_pair_across_chunks(self) -> None:
        sanitizer = QaTextSanitizer()
        assert sanitizer.feed("问题") == "问题"
        assert sanitizer.feed("`") == ""
        assert sanitizer.feed("`。") == "。"
        assert sanitizer.flush() == ""

    def test_term_wrapped_in_inline_code_is_unwrapped(self) -> None:
        sanitizer = QaTextSanitizer()
        output = sanitizer.feed("为此，作者提出了`RAG`框架") + sanitizer.flush()
        assert output == "为此，作者提出了RAG框架"

    def test_feed_inline_code_across_chunks(self) -> None:
        sanitizer = QaTextSanitizer()
        assert sanitizer.feed("`RAG-") == ""
        assert sanitizer.feed("Sequence`") == "RAG-Sequence"
        assert sanitizer.flush() == ""

    def test_feed_bold_span_across_chunks(self) -> None:
        sanitizer = QaTextSanitizer()
        assert sanitizer.feed("这是**重") == "这是"
        assert sanitizer.feed("点**内容") == "重点内容"
        assert sanitizer.flush() == ""

    def test_flush_cleans_held_backtick(self) -> None:
        sanitizer = QaTextSanitizer()
        assert sanitizer.feed("术语`") == "术语"
        assert sanitizer.flush() == ""

    def test_feed_header_marker_at_line_start(self) -> None:
        sanitizer = QaTextSanitizer()
        assert sanitizer.feed("## 标题\n正") == "标题\n正"
        assert sanitizer.flush() == ""

    def test_residual_empty_backticks_are_removed(self) -> None:
        sanitizer = QaTextSanitizer()
        output = sanitizer.feed("问题``。") + sanitizer.flush()
        assert output == "问题。"

    def test_mixed_markdown_bold_is_removed(self) -> None:
        sanitizer = QaTextSanitizer()
        output = sanitizer.feed("**核心研究问题**") + sanitizer.flush()
        assert output == "核心研究问题"


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["问题", "`", "`。"], "问题。"),
        (["`RAG-Sequence`", " 方法"], "RAG-Sequence 方法"),
        (["这是**重", "点**内容"], "这是重点内容"),
    ],
)
def test_streaming_chunk_sequences(chunks: list[str], expected: str) -> None:
    sanitizer = QaTextSanitizer()
    parts: list[str] = []
    for chunk in chunks:
        part = sanitizer.feed(chunk)
        if part:
            parts.append(part)
    tail = sanitizer.flush()
    if tail:
        parts.append(tail)
    assert sanitize_qa_answer_final("".join(parts)) == expected
