# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase F.3 schema unit tests: HSS node/edge whitelist on UnifiedPaperGraph."""

from __future__ import annotations

import pytest
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from pydantic import ValidationError
from tests.helpers.f33_hss_graphs import (
    F33_FORBIDDEN_STEM_NODE_TYPES,
    assert_hss_excludes_stem_only_node_types,
    assert_hss_schema_whitelist,
    minimal_f33_hss_graph,
)


def test_f33_minimal_hss_graph_passes_schema() -> None:
    graph = minimal_f33_hss_graph()
    assert_hss_schema_whitelist(graph)
    assert len(graph.nodes) >= 7
    assert len(graph.edges) >= 5


@pytest.mark.parametrize("stem_only_type", sorted(F33_FORBIDDEN_STEM_NODE_TYPES))
def test_f33_hss_graph_rejects_each_stem_only_node_type(stem_only_type: str) -> None:
    with pytest.raises(ValidationError, match="forbidden node types"):
        UnifiedPaperGraph(
            paper_id=f"bad-hss-{stem_only_type}",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n_stem", label="stem node", type=stem_only_type),
                GraphNode(id="n_thesis", label="论点", type=NodeType.THESIS),
            ],
            edges=[
                GraphEdge(id="e1", source="n_stem", target="n_thesis", label="REF", type="REF"),
            ],
        )


def test_f33_minimal_hss_graph_excludes_stem_only_node_types() -> None:
    assert_hss_excludes_stem_only_node_types(minimal_f33_hss_graph())


def test_f33_hss_graph_accepts_dynamic_stem_edge_type() -> None:
    """Dynamic relation invention allows uppercase SNAKE_CASE edge types across paradigms."""
    graph = UnifiedPaperGraph(
        paper_id="dynamic-hss-edge",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n_sub", label="分论点", type=NodeType.SUB_ARGUMENT),
            GraphNode(id="n_thesis", label="论点", type=NodeType.THESIS),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n_sub",
                target="n_thesis",
                label="ADDRESSES",
                type="ADDRESSES",
            ),
        ],
    )
    assert graph.edges[0].type == "ADDRESSES"


def test_f33_stem_graph_rejects_hss_node_type() -> None:
    with pytest.raises(ValidationError, match="forbidden node types"):
        UnifiedPaperGraph(
            paper_id="bad-stem",
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n1", label="lens", type=NodeType.ANALYTICAL_LENS)],
            edges=[
                GraphEdge(id="e1", source="n1", target="n1", label="RELATES_TO", type="RELATES_TO"),
            ],
        )


def test_f33_hss_graph_accepts_optional_claim_evidence_chain() -> None:
    graph = UnifiedPaperGraph(
        paper_id="hss-claim",
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n_thesis", label="核心论点", type=NodeType.THESIS),
            GraphNode(id="n_claim", label="局部主张", type=NodeType.CLAIM),
            GraphNode(id="n_evidence", label="访谈引文", type=NodeType.EVIDENCE),
        ],
        edges=[
            GraphEdge(
                id="e_supports",
                source="n_evidence",
                target="n_claim",
                label="SUPPORTS",
                type="SUPPORTS",
            ),
        ],
    )
    assert_hss_schema_whitelist(graph)


def test_f33_hss_graph_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        UnifiedPaperGraph(
            paper_id="dup-nodes",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n_dup", label="a", type=NodeType.THESIS),
                GraphNode(id="n_dup", label="b", type=NodeType.SUB_ARGUMENT),
            ],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n_dup",
                    target="n_dup",
                    label="REF",
                    type="REF",
                ),
            ],
        )


def test_f33_hss_graph_rejects_dangling_edge() -> None:
    with pytest.raises(ValidationError, match="missing node"):
        UnifiedPaperGraph(
            paper_id="dangling",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n_thesis", label="t", type=NodeType.THESIS)],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n_thesis",
                    target="n_missing",
                    label="REF",
                    type="REF",
                ),
            ],
        )
