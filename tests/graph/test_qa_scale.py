# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for question-scale detection (M2)."""

from __future__ import annotations

from backend.graph.qa import _split_incomplete_cite
from backend.llm.qa_scale import detect_question_scale, preferred_node_types
from backend.rag.models import QuestionScale
from backend.schemas.paradigm import Paradigm


def test_detect_summary_scale() -> None:
    assert detect_question_scale("这篇论文做了什么？") == "summary"


def test_detect_detail_scale() -> None:
    assert detect_question_scale("分论点如何支撑核心论点？") == "detail"


def test_detect_verification_scale_hss() -> None:
    scale = detect_question_scale(
        "核心论点通过哪些材料、经何种理论视角被论证？",
        paradigm=Paradigm.HSS,
    )
    assert scale == "verification"


def test_preferred_node_types_verification_stem() -> None:
    types = preferred_node_types(QuestionScale.VERIFICATION, paradigm=Paradigm.STEM)
    assert "Evidence" in types


def test_split_incomplete_cite_holds_partial_marker() -> None:
    split = _split_incomplete_cite("参见节点[CITE:n_l")
    assert split == ("参见节点", "[CITE:n_l")


def test_split_incomplete_cite_holds_lone_bracket() -> None:
    split = _split_incomplete_cite("节点[")
    assert split == ("节点", "[")


def test_split_incomplete_cite_returns_none_when_complete() -> None:
    assert _split_incomplete_cite("节点[CITE:n1]。") is None
