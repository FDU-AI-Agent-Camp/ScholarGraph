"""Tests for backend.graph.merge_graphs."""

from __future__ import annotations

import pytest

from backend.graph.merge_graphs import merge_edge_lists, merge_graphs, merge_node_lists
from backend.schemas.extract_phase import ExtractedEdge, ExtractedEdgeList, ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm


def _node(id: str, label: str, type: str) -> ExtractedNode:
    return ExtractedNode(id=id, label=label, type=type)


def _edge(id: str, source: str, target: str, type: str) -> ExtractedEdge:
    return ExtractedEdge(id=id, source=source, target=target, label=type, type=type)


class TestMergeNodeLists:
    def test_merges_duplicate_nodes_by_normalized_label(self) -> None:
        n1 = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[_node("n1", "CNN", "Method"), _node("n2", "ImageNet", "Dataset")],
        )
        n2 = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[_node("n1", "cnn", "Method"), _node("n3", "Adam", "Method")],
        )
        merged, id_map = merge_node_lists([n1, n2])
        assert len(merged.nodes) == 3
        assert any(n.label == "CNN" and n.type == "Method" for n in merged.nodes)
        assert id_map["c1_n1"] == id_map["c0_n1"]

    def test_preserves_distinct_nodes(self) -> None:
        n1 = ExtractedNodeList(paradigm=Paradigm.STEM, nodes=[_node("n1", "CNN", "Method")])
        n2 = ExtractedNodeList(paradigm=Paradigm.STEM, nodes=[_node("n1", "Adam", "Method")])
        merged, _ = merge_node_lists([n1, n2])
        assert len(merged.nodes) == 2

    def test_empty_input_raises(self) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            merge_node_lists([])


class TestMergeEdgeLists:
    def test_remaps_source_target_ids(self) -> None:
        edges = ExtractedEdgeList(
            paradigm=Paradigm.STEM,
            edges=[_edge("e1", "c0_n1", "c0_n2", "EVALUATED_ON")],
            node_ids=[],
        )
        id_map = {"c0_n1": "global_n1", "c0_n2": "global_n2"}
        merged = merge_edge_lists([edges], id_map)
        assert len(merged.edges) == 1
        assert merged.edges[0].source == "global_n1"
        assert merged.edges[0].target == "global_n2"

    def test_deduplicates_edges_by_key(self) -> None:
        e1 = ExtractedEdgeList(
            paradigm=Paradigm.STEM,
            edges=[_edge("e1", "c0_n1", "c0_n2", "SUPPORTS")],
        )
        e2 = ExtractedEdgeList(
            paradigm=Paradigm.STEM,
            edges=[_edge("e2", "c1_n1", "c1_n2", "SUPPORTS")],
        )
        id_map = {"c0_n1": "global_n1", "c0_n2": "global_n2", "c1_n1": "global_n1", "c1_n2": "global_n2"}
        merged = merge_edge_lists([e1, e2], id_map)
        assert len(merged.edges) == 1


class TestMergeGraphs:
    def test_combines_nodes_and_edges(self) -> None:
        n1 = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[_node("n1", "CNN", "Method"), _node("n2", "ImageNet", "Dataset")],
        )
        n2 = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[_node("n1", "cnn", "Method"), _node("n3", "Adam", "Method")],
        )
        e1 = ExtractedEdgeList(
            paradigm=Paradigm.STEM,
            edges=[_edge("e1", "c0_n1", "c0_n2", "EVALUATED_ON")],
        )
        e2 = ExtractedEdgeList(
            paradigm=Paradigm.STEM,
            edges=[_edge("e2", "c1_n1", "c1_n3", "USES_METHOD")],
        )
        graph = merge_graphs("p1", "Title", Paradigm.STEM, [n1, n2], [e1, e2])
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
        assert all(e.source in {n.id for n in graph.nodes} for e in graph.edges)
