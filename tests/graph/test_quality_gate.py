# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for graph quality gate (Plan D)."""

from __future__ import annotations

from backend.graph.quality_gate import (
    evaluate_graph_quality,
    generic_edge_ratio,
    isolated_node_ratio,
    supports_rationale_coverage,
)
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def _make_graph(
    *,
    supports_with_rationale: int,
    supports_without_rationale: int,
    isolated_nodes: int,
    generic_edges: int = 0,
) -> UnifiedPaperGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_index = 0

    for _ in range(supports_with_rationale):
        src_id = f"n{node_index}"
        nodes.append(GraphNode(id=src_id, label="sub", type="SubArgument"))
        node_index += 1
        tgt_id = f"n{node_index}"
        nodes.append(GraphNode(id=tgt_id, label="thesis", type="Thesis"))
        node_index += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src_id,
                target=tgt_id,
                label="SUPPORTS",
                type="SUPPORTS",
                rationale=f"{src_id} supports {tgt_id}",
            ),
        )

    for _ in range(supports_without_rationale):
        src_id = f"n{node_index}"
        nodes.append(GraphNode(id=src_id, label="sub", type="SubArgument"))
        node_index += 1
        tgt_id = f"n{node_index}"
        nodes.append(GraphNode(id=tgt_id, label="thesis", type="Thesis"))
        node_index += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src_id,
                target=tgt_id,
                label="SUPPORTS",
                type="SUPPORTS",
                rationale=None,
            ),
        )

    for _ in range(isolated_nodes):
        nodes.append(GraphNode(id=f"n{node_index}", label="isolated", type="ObjectOrData"))
        node_index += 1

    for _ in range(generic_edges):
        src_id = f"n{node_index}"
        nodes.append(GraphNode(id=src_id, label="src", type="SubArgument"))
        node_index += 1
        tgt_id = f"n{node_index}"
        nodes.append(GraphNode(id=tgt_id, label="tgt", type="Thesis"))
        node_index += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src_id,
                target=tgt_id,
                label="RELATES_TO",
                type="RELATES_TO",
            ),
        )

    return UnifiedPaperGraph(
        paper_id="quality-test",
        paradigm=Paradigm.HSS,
        nodes=nodes,
        edges=edges,
    )


class TestSupportsRationaleCoverage:
    def test_all_supports_have_rationale(self) -> None:
        graph = _make_graph(supports_with_rationale=4, supports_without_rationale=0, isolated_nodes=0)
        assert supports_rationale_coverage(graph) == 1.0

    def test_half_supports_missing_rationale(self) -> None:
        graph = _make_graph(supports_with_rationale=1, supports_without_rationale=1, isolated_nodes=0)
        assert supports_rationale_coverage(graph) == 0.5

    def test_no_supports_edges_returns_one(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="no-supports",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
            edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
        )
        assert supports_rationale_coverage(graph) == 1.0

    def test_empty_rationale_string_counts_as_missing(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="empty-rationale",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n1", label="evidence", type="Evidence"),
                GraphNode(id="n2", label="claim", type="Claim"),
            ],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n1",
                    target="n2",
                    label="SUPPORTS",
                    type="SUPPORTS",
                    rationale="   ",
                ),
            ],
        )
        assert supports_rationale_coverage(graph) == 0.0


class TestIsolatedNodeRatio:
    def test_no_isolated_nodes(self) -> None:
        graph = _make_graph(supports_with_rationale=1, supports_without_rationale=0, isolated_nodes=0)
        assert isolated_node_ratio(graph) == 0.0

    def test_half_nodes_isolated(self) -> None:
        graph = _make_graph(supports_with_rationale=1, supports_without_rationale=0, isolated_nodes=2)
        # 2 connected + 2 isolated = 4 nodes
        assert isolated_node_ratio(graph) == 0.5

    def test_empty_graph(self) -> None:
        graph = UnifiedPaperGraph(paper_id="empty", paradigm=Paradigm.HSS, nodes=[], edges=[])
        assert isolated_node_ratio(graph) == 0.0


class TestEvaluateGraphQuality:
    def test_passes_when_both_metrics_ok(self) -> None:
        graph = _make_graph(supports_with_rationale=1, supports_without_rationale=0, isolated_nodes=0)
        passed, reasons = evaluate_graph_quality(
            graph,
            min_supports_rationale_coverage=0.5,
            max_isolated_node_ratio=0.4,
        )
        assert passed is True
        assert reasons == []

    def test_fails_on_low_rationale_coverage(self) -> None:
        graph = _make_graph(supports_with_rationale=1, supports_without_rationale=3, isolated_nodes=0)
        passed, reasons = evaluate_graph_quality(
            graph,
            min_supports_rationale_coverage=0.5,
            max_isolated_node_ratio=0.4,
        )
        assert passed is False
        assert any("rationale coverage" in reason for reason in reasons)

    def test_fails_on_high_isolated_ratio(self) -> None:
        graph = _make_graph(supports_with_rationale=1, supports_without_rationale=0, isolated_nodes=3)
        # 2 connected + 3 isolated = 5 nodes -> 60% isolated
        passed, reasons = evaluate_graph_quality(
            graph,
            min_supports_rationale_coverage=0.5,
            max_isolated_node_ratio=0.4,
        )
        assert passed is False
        assert any("isolated node ratio" in reason for reason in reasons)

    def test_fails_on_both_metrics(self) -> None:
        graph = _make_graph(supports_with_rationale=1, supports_without_rationale=3, isolated_nodes=6)
        # 8 connected + 6 isolated = 14 nodes -> ~43% isolated
        passed, reasons = evaluate_graph_quality(
            graph,
            min_supports_rationale_coverage=0.5,
            max_isolated_node_ratio=0.4,
        )
        assert passed is False
        assert len(reasons) == 2

    def test_fails_on_high_generic_edge_ratio(self) -> None:
        graph = _make_graph(
            supports_with_rationale=2,
            supports_without_rationale=0,
            isolated_nodes=0,
            generic_edges=2,
        )
        passed, reasons = evaluate_graph_quality(
            graph,
            min_supports_rationale_coverage=0.5,
            max_isolated_node_ratio=0.4,
            max_generic_edge_ratio=0.3,
        )
        assert passed is False
        assert any("generic edge ratio" in reason for reason in reasons)


class TestGenericEdgeRatio:
    def test_no_generic_edges_returns_zero(self) -> None:
        graph = _make_graph(supports_with_rationale=2, supports_without_rationale=0, isolated_nodes=0)
        assert generic_edge_ratio(graph) == 0.0

    def test_half_generic_edges(self) -> None:
        graph = _make_graph(
            supports_with_rationale=1,
            supports_without_rationale=0,
            isolated_nodes=0,
            generic_edges=1,
        )
        assert generic_edge_ratio(graph) == 0.5
