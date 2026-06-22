"""Structured classifier-input extraction tests (BE-1)."""

from __future__ import annotations

from backend.ingest.snippets import (
    MAX_CLASSIFIER_INPUT_CHARS,
    build_classifier_input,
    normalize_for_sections,
    normalize_whitespace,
    parse_classifier_sections,
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

    assert "Title:" in result
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


ENRICHED_INPUT = """
Title: Sample Paper

Abstract: We study social memory using interviews.

Keywords: memory, society

Introduction: Previous work debated this topic.

Conclusion:
This work advances historical understanding.
Future studies should examine archives.

Meta-Information:
Journal: Social History Review
Funding: National Humanities Grant
Affiliation: Department of History, Example University
Research Object: social memory in post-war communities
Methodology/Tool: oral history interviews
Core Intellectual Contribution: reveals how collective memory shapes identity
"""


def test_parse_classifier_sections_recover_all_fields() -> None:
    sections = parse_classifier_sections(ENRICHED_INPUT)
    assert sections.title == "Sample Paper"
    assert "social memory" in sections.abstract
    assert sections.keywords == "memory, society"
    assert "Previous work" in sections.intro
    assert "historical understanding" in sections.conclusion
    assert sections.journal == "Social History Review"
    assert sections.funding == "National Humanities Grant"
    assert sections.affiliation == "Department of History, Example University"
    assert sections.research_object == "social memory in post-war communities"
    assert sections.methodology_tool == "oral history interviews"
    assert "collective memory shapes identity" in sections.core_intellectual_contribution


def test_build_classifier_input_with_full_text_extracts_conclusion() -> None:
    head = (
        "Memory Study\n\n"
        "Abstract\nWe study memory.\n\n"
        "Keywords\nmemory\n\n"
        "Introduction\nPrior work exists."
    )
    full = (
        "Memory Study\n\n"
        "Abstract\nWe study memory.\n\n"
        "Keywords\nmemory\n\n"
        "Introduction\nPrior work exists.\n\n"
        "Methods\nWe interviewed people.\n\n"
        "Conclusion\nThis advances our understanding of collective memory.\n\n"
        "References\n[1] Author."
    )
    result = build_classifier_input(head, full_text=full)
    assert "Conclusion:" in result
    assert "collective memory" in result
    # Conclusion should appear before Introduction to survive truncation.
    assert result.index("Conclusion:") < result.index("Introduction:")


def test_build_classifier_input_includes_meta_information() -> None:
    text = (
        "Social History Review\n\n"
        "Memory Study\n\n"
        "Author: Alice, Department of History, Example University\n\n"
        'Funding: National Humanities Grant "Oral Histories Project"\n\n'
        "Abstract\nWe study memory."
    )
    result = build_classifier_input(text)
    assert "Meta-Information:" in result
    assert "Social History Review" in result
    assert "Department of History" in result
    assert "Oral Histories Project" in result


def test_format_classifier_input_includes_core_contribution_fields() -> None:
    from backend.ingest.snippets import format_classifier_input

    result = format_classifier_input(
        title="Sherpa Phylogeography",
        abstract="We analyze Sherpa Y-chromosome data.",
        journal="Human Genetics",
        research_object="Sherpa male-line ancestry",
        methodology_tool="Y-chromosome sequencing",
        core_intellectual_contribution="argues the Dangxiang Qiang are Sherpa ancestors",
    )
    assert result.startswith("Meta-Information:")
    assert "Research Object: Sherpa male-line ancestry" in result
    assert "Methodology/Tool: Y-chromosome sequencing" in result
    assert "Core Intellectual Contribution: argues the Dangxiang Qiang are Sherpa ancestors" in result
    assert "Title: Sherpa Phylogeography" in result
