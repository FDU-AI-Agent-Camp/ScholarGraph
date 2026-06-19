"""Tests for backend.schemas.extract_phase validation hooks."""

from __future__ import annotations

import pytest
from backend.schemas.extract_phase import (
    ExtractedEdge,
    ExtractedEdgeList,
    ExtractedGraph,
    ExtractedNode,
    ExtractedNodeList,
)
from backend.schemas.paradigm import Paradigm


def _hss_node(**overrides: object) -> ExtractedNode:
    defaults = {"id": "n1", "label": "Thesis", "type": "Thesis"}
    defaults.update(overrides)
    return ExtractedNode(**defaults)


def _hss_edge(**overrides: object) -> ExtractedEdge:
    defaults = {"id": "e1", "source": "n1", "target": "n1", "label": "supports", "type": "SUPPORTS"}
    defaults.update(overrides)
    return ExtractedEdge(**defaults)


class TestExtractedNodeList:
    def test_valid_hss_nodes_pass(self) -> None:
        node_list = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[_hss_node()],
        )
        assert len(node_list.nodes) == 1

    def test_duplicate_node_ids_raise(self) -> None:
        with pytest.raises(ValueError, match="Duplicate node ids"):
            ExtractedNodeList(
                paradigm=Paradigm.HSS,
                nodes=[_hss_node(id="n1"), _hss_node(id="n1", label="Other")],
            )

    def test_forbidden_hss_node_type_raises(self) -> None:
        with pytest.raises(ValueError, match="forbidden node types"):
            ExtractedNodeList(
                paradigm=Paradigm.HSS,
                nodes=[_hss_node(type="Method")],
            )

    def test_valid_stem_node_type_passes(self) -> None:
        node_list = ExtractedNodeList(
            paradigm=Paradigm.STEM,
            nodes=[_hss_node(type="Method")],
        )
        assert node_list.nodes[0].type == "Method"


class TestExtractedEdgeList:
    def test_valid_hss_edges_pass(self) -> None:
        edge_list = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_hss_edge()],
            node_ids=["n1"],
        )
        assert len(edge_list.edges) == 1

    def test_duplicate_edge_ids_raise(self) -> None:
        with pytest.raises(ValueError, match="Duplicate edge ids"):
            ExtractedEdgeList(
                paradigm=Paradigm.HSS,
                edges=[_hss_edge(id="e1"), _hss_edge(id="e1")],
                node_ids=["n1"],
            )

    def test_forbidden_hss_edge_type_raises(self) -> None:
        with pytest.raises(ValueError, match="forbidden edge types"):
            ExtractedEdgeList(
                paradigm=Paradigm.HSS,
                edges=[_hss_edge(type="USES")],
                node_ids=["n1"],
            )

    def test_dangling_edge_reference_raises(self) -> None:
        with pytest.raises(ValueError, match="Edges reference missing nodes"):
            ExtractedEdgeList(
                paradigm=Paradigm.HSS,
                edges=[_hss_edge(source="n1", target="n2")],
                node_ids=["n1"],
            )

    def test_empty_edge_list_passes(self) -> None:
        edge_list = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[],
            node_ids=["n1"],
        )
        assert edge_list.edges == []


class TestExtractedGraph:
    def test_valid_graph_passes(self) -> None:
        graph = ExtractedGraph(
            paper_id="paper-001",
            paradigm=Paradigm.HSS,
            nodes=[_hss_node()],
            edges=[_hss_edge()],
        )
        assert graph.paper_id == "paper-001"

    def test_duplicate_node_ids_in_graph_raise(self) -> None:
        with pytest.raises(ValueError, match="Duplicate node ids"):
            ExtractedGraph(
                paper_id="paper-001",
                paradigm=Paradigm.HSS,
                nodes=[_hss_node(id="n1"), _hss_node(id="n1", label="Other")],
                edges=[],
            )

    def test_dangling_edge_in_graph_raises(self) -> None:
        with pytest.raises(ValueError, match="references missing node"):
            ExtractedGraph(
                paper_id="paper-001",
                paradigm=Paradigm.HSS,
                nodes=[_hss_node()],
                edges=[_hss_edge(target="n2")],
            )

    def test_forbidden_node_type_in_graph_raises(self) -> None:
        with pytest.raises(ValueError, match="Forbidden node types"):
            ExtractedGraph(
                paper_id="paper-001",
                paradigm=Paradigm.HSS,
                nodes=[_hss_node(type="Method")],
                edges=[],
            )

    def test_forbidden_edge_type_in_graph_raises(self) -> None:
        with pytest.raises(ValueError, match="Forbidden edge types"):
            ExtractedGraph(
                paper_id="paper-001",
                paradigm=Paradigm.HSS,
                nodes=[_hss_node()],
                edges=[_hss_edge(type="USES")],
            )
