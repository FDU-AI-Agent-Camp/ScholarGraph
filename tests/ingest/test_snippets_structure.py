"""Structured classifier-input extraction tests (BE-1)."""

from __future__ import annotations

from backend.ingest.snippets import (
    MAX_CLASSIFIER_INPUT_CHARS,
    build_classifier_input,
    normalize_for_sections,
    normalize_whitespace,
)

NATURE_STYLE = """
Article
https://doi.org/10.1038/example
Crystal Property Prediction with Deep Learning
to Improve Materials Discovery
Alice Author1 & Bob Author2
1University of Example, China.

Accelerating the discovery of novel crystal materials by machine learning is
crucial for advancing clean energy technologies and information processing.
We proposed universal atomic embeddings and validated them on public datasets.

The development of deep learning has created research methods for materials science.
Many graph neural network models have been proposed for property prediction.
Further experiments compare CGCNN and ALIGNN baselines on formation energy tasks.
"""

EXPLICIT_STEM = """
Sample Agent Framework Paper
Jane Doe, MIT

Abstract
We evaluate our agent framework on benchmark datasets with accuracy metrics.
Results show consistent gains over strong baselines across three tasks.

Keywords
agent, large language model, benchmark

Introduction
Recent work on tool-using agents has improved multi-step reasoning.
Our framework combines ReAct-style planning with retrieval augmentation.
We report ablations on three academic QA datasets.
"""

THESIS_STYLE = """
当代中国电影的政治传播变迁研究
作者：张三

摘要：本文考察改革开放以来中国电影政治传播方式的演变，
分析意识形态、市场与受众之间的张力，并提出类型学框架。

关键词：电影；政治传播；意识形态；受众

一、前言
中国电影在特定历史阶段承担着独特的传播功能。
学界对此已有多种解释路径，但缺乏系统的类型比较。
本文尝试从政治传播理论出发重新梳理这一议题。
"""


def test_normalize_for_sections_keeps_line_breaks_for_headers() -> None:
    raw = "Title line\n\nAbstract\nBody text"
    assert normalize_for_sections(raw) == "Title line\nAbstract\nBody text"


def test_build_classifier_input_nature_style_implicit_abstract() -> None:
    result = build_classifier_input(NATURE_STYLE)

    assert result.startswith("Title:")
    assert "Crystal Property Prediction" in result
    assert "Abstract:" in result
    assert "CGCNN" in result or "ALIGNN" in result
    assert "deep learning" in result.lower()


def test_build_classifier_input_explicit_stem_section_order() -> None:
    result = build_classifier_input(EXPLICIT_STEM)

    title_index = result.index("Title:")
    abstract_index = result.index("Abstract:")
    keywords_index = result.index("Keywords:")
    intro_index = result.index("Introduction:")

    assert title_index < abstract_index < keywords_index < intro_index
    assert "agent framework" in result
    assert "ReAct" in result


def test_build_classifier_input_thesis_chinese_sections() -> None:
    result = build_classifier_input(THESIS_STYLE)

    assert "Title:" in result
    assert "电影" in result
    assert "Abstract:" in result
    assert "政治传播" in result
    assert "Keywords:" in result
    assert "意识形态" in result
    assert "Introduction:" in result
    assert "类型比较" in result


def test_build_classifier_input_truncates_to_max_length() -> None:
    long_body = "x" * (MAX_CLASSIFIER_INPUT_CHARS + 500)
    plain = f"Only header\n{long_body}"

    result = build_classifier_input(plain)

    assert len(result) <= MAX_CLASSIFIER_INPUT_CHARS


def test_build_classifier_input_preserves_intro_paragraph_limit() -> None:
    intro_paragraphs = "\n".join(f"Intro paragraph {index} with extra detail." for index in range(10))
    text = f"""
Paper Title

Abstract
Short abstract for classifier testing purposes only.

Keywords
test

Introduction
{intro_paragraphs}
"""
    result = build_classifier_input(text)

    assert "Introduction:" in result
    assert "Intro paragraph 0" in result
    assert "Intro paragraph 9" not in result


def test_normalize_whitespace_on_multiline_block() -> None:
    assert normalize_whitespace("  hello   world  \n\n\n\n  foo ") == "hello world\n\nfoo"
