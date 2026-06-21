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


class TestHeuristicPruning:
    def test_zero_degree_nodes_are_removed(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                _node("c0_n1", "Main Claim", "Claim"),
                _node("c0_n2", "Orphan Evidence", "Evidence"),
                _node("c0_n3", "Supporting Claim", "Claim"),
            ],
        )
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_edge("e1", "c0_n1", "c0_n3", "SUPPORTS")],
        )
        graph = merge_graphs(
            "p1", "Title", Paradigm.HSS, [nodes], [edges], prune=True, node_ids_prefixed=True
        )

        assert len(graph.nodes) == 2
        assert {n.id for n in graph.nodes} == {"c0_n1", "c0_n3"}
        assert any("PRUNED_ZERO_DEGREE:1" in w for w in graph.warnings)

    def test_leaf_evidence_is_folded_into_parent_claim(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                _node("c0_n1", "Main Claim", "Claim"),
                _node("c0_n2", "Survey data", "Evidence"),
            ],
        )
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_edge("e1", "c0_n2", "c0_n1", "SUPPORTS")],
        )
        graph = merge_graphs(
            "p1", "Title", Paradigm.HSS, [nodes], [edges], prune=True, node_ids_prefixed=True
        )

        assert len(graph.nodes) == 1
        assert graph.nodes[0].id == "c0_n1"
        assert len(graph.edges) == 0
        assert any("FOLDED_LEAVES:1" in w for w in graph.warnings)
        folded = graph.nodes[0].data.get("folded_leaves", [])
        assert len(folded) == 1
        assert folded[0]["leaf_id"] == "c0_n2"
        assert folded[0]["leaf_type"] == "Evidence"

    def test_leaf_pair_is_not_ambiguously_folded(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                _node("c0_n1", "Evidence A", "Evidence"),
                _node("c0_n2", "Evidence B", "Evidence"),
            ],
        )
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_edge("e1", "c0_n1", "c0_n2", "RELATES_TO")],
        )
        graph = merge_graphs(
            "p1", "Title", Paradigm.HSS, [nodes], [edges], prune=True, node_ids_prefixed=True
        )

        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert not any("FOLDED_LEAVES" in w for w in graph.warnings)

    def test_non_leaf_nodes_are_not_folded(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                _node("c0_n1", "Thesis", "Thesis"),
                _node("c0_n2", "Sub Argument", "SubArgument"),
            ],
        )
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_edge("e1", "c0_n2", "c0_n1", "SUB_ARGUMENT_OF")],
        )
        graph = merge_graphs(
            "p1", "Title", Paradigm.HSS, [nodes], [edges], prune=True, node_ids_prefixed=True
        )

        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert not any("FOLDED_LEAVES" in w for w in graph.warnings)


class TestSanitizeGraphLabels:
    def test_garbled_label_is_replaced_with_type_fallback(self) -> None:
        garbled = "\ufffd" * 5
        # Use non-foldable types (Claim <-> Thesis) so both nodes survive pruning.
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                _node("c0_n1", "Main Claim", "Claim"),
                ExtractedNode(id="c0_n2", label=garbled, type="Thesis"),
            ],
        )
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_edge("e1", "c0_n1", "c0_n2", "SUPPORTS")],
        )
        graph = merge_graphs(
            "p1", "Title", Paradigm.HSS, [nodes], [edges], prune=True, node_ids_prefixed=True
        )

        assert len(graph.nodes) == 2
        garbled_node = next(n for n in graph.nodes if n.id == "c0_n2")
        assert garbled_node.label == "[Thesis]"
        assert garbled_node.data.get("original_label") == garbled
        assert garbled_node.data.get("label_sanitized") is True
        assert any("GARBLED_LABELS_SANITIZED:1" in w for w in graph.warnings)

    def test_high_replacement_ratio_is_sanitized(self) -> None:
        # 60% replacement characters triggers the ratio rule.
        garbled = "abc" + "\ufffd" * 5
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[_node("c0_n1", garbled, "Claim")],
        )
        # Add a self-loop-like edge so the node is not zero-degree pruned.
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_edge("e1", "c0_n1", "c0_n1", "RELATES_TO")],
        )
        graph = merge_graphs(
            "p1", "Title", Paradigm.HSS, [nodes], [edges], prune=True, node_ids_prefixed=True
        )

        assert len(graph.nodes) == 1
        assert graph.nodes[0].label == "[Claim]"

    def test_clean_label_is_unchanged(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[_node("c0_n1", "情感共鸣转向", "Claim")],
        )
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_edge("e1", "c0_n1", "c0_n1", "RELATES_TO")],
        )
        graph = merge_graphs(
            "p1", "Title", Paradigm.HSS, [nodes], [edges], prune=True, node_ids_prefixed=True
        )

        assert len(graph.nodes) == 1
        assert graph.nodes[0].label == "情感共鸣转向"
        assert "GARBLED_LABELS_SANITIZED" not in graph.warnings
