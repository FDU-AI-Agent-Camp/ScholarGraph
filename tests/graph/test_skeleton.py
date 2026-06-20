"""Tests for backend.graph.skeleton downsampling."""

from __future__ import annotations

import pytest

from backend.graph.skeleton import DEFAULT_MAX_SKELETON_NODES, build_skeleton_graph
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def _node(node_id: str) -> GraphNode:
    return GraphNode(id=node_id, label=node_id, type="Claim")


def _edge(edge_id: str, source: str, target: str) -> GraphEdge:
    return GraphEdge(id=edge_id, source=source, target=target, label="supports", type="RELATES_TO")


class TestBuildSkeletonGraph:
    def test_keeps_only_giant_component(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=[_node("a1"), _node("a2"), _node("b1")],
            edges=[_edge("e1", "a1", "a2")],
        )
        result = build_skeleton_graph(graph)
        assert {n.id for n in result.nodes} == {"a1", "a2"}
        assert len(result.edges) == 1

    def test_applies_degree_cutoff_when_giant_component_too_large(self) -> None:
        nodes = [_node(f"n{i}") for i in range(DEFAULT_MAX_SKELETON_NODES + 50)]
        # Build a line graph: all nodes connected, degrees low except ends.
        edges = [_edge(f"e{i}", f"n{i}", f"n{i + 1}",) for i in range(len(nodes) - 1)]
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=nodes,
            edges=edges,
        )
        result = build_skeleton_graph(graph)
        assert len(result.nodes) == DEFAULT_MAX_SKELETON_NODES
        assert all(edge.source in {n.id for n in result.nodes} for edge in result.edges)
        assert all(edge.target in {n.id for n in result.nodes} for edge in result.edges)

    def test_prefers_high_degree_nodes_in_cutoff(self) -> None:
        nodes = [_node("hub"), *[_node(f"leaf{i}") for i in range(DEFAULT_MAX_SKELETON_NODES)]]
        edges = [_edge(f"e{i}", "hub", f"leaf{i}") for i in range(DEFAULT_MAX_SKELETON_NODES)]
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=nodes,
            edges=edges,
        )
        result = build_skeleton_graph(graph)
        assert len(result.nodes) == DEFAULT_MAX_SKELETON_NODES
        # Hub has the highest degree and must survive.
        assert any(n.id == "hub" for n in result.nodes)

    def test_empty_graph_returns_empty(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="p1",
            paradigm=Paradigm.HSS,
            nodes=[],
            edges=[],
        )
        result = build_skeleton_graph(graph)
        assert result.nodes == []
        assert result.edges == []

    def test_preserves_metadata(self) -> None:
        graph = UnifiedPaperGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.HSS,
            summary="S",
            nodes=[_node("a")],
            edges=[],
        )
        result = build_skeleton_graph(graph)
        assert result.paper_id == "p1"
        assert result.title == "T"
        assert result.summary == "S"
