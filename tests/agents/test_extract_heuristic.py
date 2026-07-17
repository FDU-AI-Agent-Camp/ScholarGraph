# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests: heuristic graph fallback (extract_heuristic.py)."""

from __future__ import annotations

from backend.agents.extract_heuristic import (
    build_heuristic_graph,
    build_hss_graph,
    build_stem_graph,
    extract_title,
    paper_id_for_text,
)
from backend.schemas import NodeType
from backend.schemas.graph import HSS_NODE_TYPES, STEM_NODE_TYPES
from backend.schemas.paradigm import Paradigm


def test_extract_title_reads_chinese_prefix() -> None:
    title = extract_title("标题：近代通商口岸制度演变研究\n正文")
    assert "通商口岸" in title


def test_extract_title_reads_first_line_when_no_prefix() -> None:
    title = extract_title("Agent Framework Benchmark\nAbstract")
    assert title == "Agent Framework Benchmark"


def test_paper_id_for_text_is_stable() -> None:
    assert paper_id_for_text("same") == paper_id_for_text("same")
    assert paper_id_for_text("a") != paper_id_for_text("b")


def test_build_hss_graph_has_thesis_and_sub_arguments() -> None:
    graph = build_hss_graph(
        "标题：测试\n本文认为核心论点成立。首先，分论点一。其次，分论点二。",
        "测试",
    )
    types = {node.type for node in graph.nodes}
    assert NodeType.THESIS in types
    assert NodeType.SUB_ARGUMENT in types
    assert types <= HSS_NODE_TYPES
    assert any(edge.type == "SUB_ARGUMENT_OF" for edge in graph.edges)


def test_build_stem_graph_has_verification_chain() -> None:
    graph = build_stem_graph(
        "Title: ML\nWe study the task. The method uses a model. "
        "Experiments on datasets with accuracy metrics and baseline comparison.",
        "ML",
    )
    types = {node.type for node in graph.nodes}
    assert NodeType.METHOD in types
    assert NodeType.EVIDENCE in types
    assert types <= STEM_NODE_TYPES
    assert any(edge.type == "SUPPORTS" for edge in graph.edges)


def test_build_heuristic_graph_dispatches_by_paradigm() -> None:
    hss = build_heuristic_graph("本文认为……", Paradigm.HSS)
    stem = build_heuristic_graph("method dataset benchmark", Paradigm.STEM)
    assert hss.paradigm == Paradigm.HSS
    assert stem.paradigm == Paradigm.STEM
