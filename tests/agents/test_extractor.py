# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for BE-2 graph extractor."""

from __future__ import annotations

import asyncio

from backend.agents import extract
from backend.schemas import NodeType, Paradigm
from backend.schemas.graph import HSS_NODE_TYPES, STEM_NODE_TYPES


def run_async(coro):
    return asyncio.run(coro)


def test_extracts_valid_hss_graph_without_stem_only_nodes() -> None:
    result = run_async(
        extract(
            """
            标题：近代通商口岸制度演变研究
            本文认为，通商口岸的制度演变需要放在历史制度主义视角下理解。
            既有研究忽略了地方档案材料中的路径依赖。
            首先，地方制度塑造了商业网络。
            其次，档案材料揭示了国家与商人的协商过程。
            """,
            Paradigm.HSS,
        )
    )
    graph = result.graph

    node_types = {node.type for node in graph.nodes}
    assert graph.paradigm == Paradigm.HSS.value
    assert node_types <= {node_type.value for node_type in HSS_NODE_TYPES}
    assert NodeType.METRIC.value not in node_types
    assert any(edge.type == "SUB_ARGUMENT_OF" for edge in graph.edges)
    assert set(edge.source for edge in graph.edges) <= {node.id for node in graph.nodes}


def test_extracts_valid_stem_graph_without_hss_only_nodes() -> None:
    result = run_async(
        extract(
            """
            Title: Agent Framework Benchmark
            We study the task of multi-agent paper reading. The method uses a retrieval model and
            planning algorithm. Experiments evaluate datasets with accuracy and F1 metrics, compare
            against a baseline, and show improved performance.
            """,
            Paradigm.STEM,
        )
    )
    graph = result.graph

    node_types = {node.type for node in graph.nodes}
    assert graph.paradigm == Paradigm.STEM.value
    assert node_types <= {node_type.value for node_type in STEM_NODE_TYPES}
    assert NodeType.ANALYTICAL_LENS.value not in node_types
    assert any(edge.type == "SUPPORTS" for edge in graph.edges)
    assert set(edge.target for edge in graph.edges) <= {node.id for node in graph.nodes}
