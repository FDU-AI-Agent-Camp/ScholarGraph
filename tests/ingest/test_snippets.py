"""Unit tests for classifier input slicing (BE-1)."""

from backend.ingest.snippets import build_classifier_input, normalize_whitespace

STEM_SAMPLE = """
Article
Transformer-generated atomic embeddings to enhance prediction accuracy
Luozhijie Jin and Hao Zhang

Abstract
Accelerating the discovery of novel crystal materials by machine learning is crucial.
We proposed universal atomic embeddings and demonstrated improved accuracy on CGCNN.

Keywords
machine learning, materials science, crystal properties

Introduction
The development of deep learning has created research methods for materials science.
Many graph neural network models have been proposed for property prediction.
In this work we focus on atomic fingerprints for multi-task learning.
"""

HSS_SAMPLE = """
西夏研究
再探夏尔巴人父系历史
洛桑塔杰

摘要：夏尔巴人是生活于我国和尼泊尔交界地区的少数民族，其族源问题在学术界颇有争议。
本文根据 Y-STR 和 Y-SNP 数据进行遗传分析，并结合历史文献探讨夏尔巴人父系历史。

关键词：夏尔巴人；分子历史；Y染色体；遗传谱系分析

一、前言
夏尔巴人在藏语中意为“来自东方的人”，主要生活于我国和尼泊尔、印度交界的边境地区。
关于夏尔巴人的族源问题，学术界主要有三种观点。
本文通过对夏尔巴人 Y 染色体数据进行综合分析，对族群历史进行再探讨。
"""


def test_normalize_whitespace_collapses_blank_lines() -> None:
    assert normalize_whitespace("a  b\n\n\n\nc") == "a b\n\nc"


def test_build_classifier_input_stem_sections() -> None:
    result = build_classifier_input(STEM_SAMPLE)
    assert "Title:" in result
    assert "atomic embeddings" in result
    assert "Abstract:" in result
    assert "machine learning" in result
    assert "Keywords:" in result
    assert "materials science" in result
    assert "Introduction:" in result
    assert "graph neural network" in result


def test_build_classifier_input_hss_sections() -> None:
    result = build_classifier_input(HSS_SAMPLE)
    assert "Title:" in result
    assert "夏尔巴" in result
    assert "Abstract:" in result
    assert "族源" in result
    assert "Keywords:" in result
    assert "Y染色体" in result
    assert "Introduction:" in result
    assert "三种观点" in result


def test_build_classifier_input_empty_returns_empty() -> None:
    assert build_classifier_input("") == ""
    assert build_classifier_input("   \n  ") == ""


def test_build_classifier_input_fallback_without_markers() -> None:
    plain = "Only a short document without section headers."
    assert build_classifier_input(plain) == plain
