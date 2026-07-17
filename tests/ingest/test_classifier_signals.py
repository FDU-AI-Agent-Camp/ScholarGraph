# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for conclusion / meta signal extraction (BE-1 extension)."""

from __future__ import annotations

from backend.ingest.classifier_signals import (
    _looks_like_journal_line,
    extract_conclusion_tail,
    extract_meta_info,
)


def test_extract_conclusion_tail_english() -> None:
    text = """
Introduction
We study memory.

Methods
We ran experiments.

Conclusion
This reveals the social construction of collective memory.
Future work should compare regional archives.

References
[1] Author, Journal, 2020.
"""
    conclusion = extract_conclusion_tail(text)
    assert "collective memory" in conclusion
    assert "regional archives" in conclusion
    assert "References" not in conclusion


def test_extract_conclusion_tail_chinese() -> None:
    text = """
一、引言
本文研究族源。

二、讨论
夏尔巴人的族群记忆可能是多次塑造的结果。

三、结论
本研究有助于理解喜马拉雅地区的人群历史。
后续可结合考古发现深化讨论。

参考文献
[1] ...
"""
    conclusion = extract_conclusion_tail(text)
    assert "喜马拉雅" in conclusion
    assert "考古" in conclusion
    assert "参考文献" not in conclusion


def test_extract_conclusion_tail_no_heading_returns_empty() -> None:
    text = "Only a short plain document without any conclusion section."
    assert extract_conclusion_tail(text) == ""


def test_extract_conclusion_tail_stops_at_references() -> None:
    text = """
Conclusion
First conclusion paragraph.
Second conclusion paragraph.

References
[1] Citation.
"""
    conclusion = extract_conclusion_tail(text)
    assert "First conclusion" in conclusion
    assert "Second conclusion" in conclusion
    assert "Citation" not in conclusion


def test_extract_meta_info_hss_sample() -> None:
    text = """
西夏研究

再探夏尔巴人父系历史

作者简介：洛桑塔杰，男，复旦大学文物与博物馆学系本科生，主要研究方向为分子考古。

基金项目：宁夏古代人类与动物骨骼考古新方法的应用示范研究
（项目批准号：2020BFG02008）
"""
    meta = extract_meta_info(text)
    assert meta["journal"] == "西夏研究"
    assert "文物与博物馆学系" in meta["affiliation"]
    assert "古代人类与动物骨骼考古新方法" in meta["funding"]


def test_extract_meta_info_funding_prefers_quoted_project() -> None:
    text = "基金项目：某省科技厅重点研发计划项目“古代DNA与考古学整合研究”资助。"
    meta = extract_meta_info(text)
    assert "古代DNA与考古学整合研究" in meta["funding"]


def test_extract_meta_info_affiliation_english() -> None:
    text = "1Department of Materials Science, MIT, Cambridge, MA."
    meta = extract_meta_info(text)
    assert "MIT" in meta["affiliation"]


def test_extract_meta_info_journal_explicit_label() -> None:
    text = "Journal: Nature Communications\n\nTitle: Some paper"
    meta = extract_meta_info(text)
    assert meta["journal"] == "Nature Communications"


def test_looks_like_journal_line() -> None:
    assert _looks_like_journal_line("西夏研究") is True
    assert _looks_like_journal_line("Nature Communications") is True
    assert _looks_like_journal_line("Transformer-generated atomic embeddings") is False
    assert _looks_like_journal_line("DOI: 10.1000/example") is False


def test_extract_meta_info_does_not_over_extract_title_as_journal() -> None:
    text = """
Transformer-generated atomic embeddings to enhance prediction accuracy
Jane Doe, MIT

Abstract
We propose a method.
"""
    meta = extract_meta_info(text)
    assert meta["journal"] == ""
    assert meta["affiliation"] == ""


def test_extract_meta_info_empty_text() -> None:
    assert extract_meta_info("") == {"journal": "", "funding": "", "affiliation": ""}
