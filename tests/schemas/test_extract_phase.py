# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for backend.schemas.extract_phase validation hooks."""

from __future__ import annotations

import json

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

    def test_overly_long_label_is_truncated_with_ellipsis(self) -> None:
        long_label = "A" * 200
        node_list = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[_hss_node(label=long_label)],
        )
        assert node_list.nodes[0].label.endswith("...")
        assert len(node_list.nodes[0].label) == 120

    def test_overly_long_source_span_is_truncated_with_ellipsis(self) -> None:
        long_span = "B" * 600
        node_list = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[_hss_node(source_span=long_span)],
        )
        assert node_list.nodes[0].source_span.endswith("...")
        assert len(node_list.nodes[0].source_span) == 500

    def test_truncation_records_warning_in_context(self) -> None:
        long_label = "A" * 200
        warnings: list[str] = []
        raw_payload = json.dumps(
            {
                "paradigm": Paradigm.HSS.value,
                "warnings": [],
                "nodes": [
                    {
                        "id": "n1",
                        "label": long_label,
                        "type": "Thesis",
                        "source_span": "span",
                    }
                ],
            }
        )
        result = ExtractedNodeList.model_validate_json(raw_payload, context={"warnings": warnings})
        assert result.warnings == warnings
        assert "extract_field_truncated:node.label" in warnings


class TestExtractedEdgeList:
    def test_valid_hss_edges_pass(self) -> None:
        edge_list = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_hss_edge()],
            node_ids=["n1"],
        )
        assert len(edge_list.edges) == 1

    def test_duplicate_edge_ids_are_deduplicated_with_warning(self) -> None:
        edge_list = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[_hss_edge(id="e1"), _hss_edge(id="e1")],
            node_ids=["n1"],
        )
        assert len(edge_list.edges) == 1
        assert any("DUPLICATE_EDGE_IDS_DEDUPLICATED" in w for w in edge_list.warnings)

    def test_invalid_hss_edge_type_format_raises(self) -> None:
        with pytest.raises(ValueError, match="forbidden edge types"):
            ExtractedEdgeList(
                paradigm=Paradigm.HSS,
                edges=[_hss_edge(type="InvalidType")],
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

    def test_edge_with_missing_confidence_is_accepted_in_list(self) -> None:
        edge = _hss_edge(confidence=None)  # type: ignore[call-arg]
        edge_list = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[edge],
            node_ids=["n1"],
        )
        assert edge_list.edges[0].confidence == "MEDIUM"
        assert edge_list.edges[0].data.get("confidence_missing") is True


class TestExtractedEdgeCoreQuality:
    def test_core_edge_missing_rationale_is_flagged(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            source_span="some span",
        )
        assert edge.data.get("rationale_missing") is True
        assert edge.data.get("incomplete") is True

    def test_core_edge_missing_source_span_is_flagged(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            rationale="some rationale",
        )
        assert edge.data.get("rationale_missing") is True
        assert edge.data.get("incomplete") is True

    def test_core_edge_with_all_fields_is_not_flagged(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            rationale="some rationale",
            source_span="some span",
            confidence="HIGH",
        )
        assert "rationale_missing" not in edge.data
        assert "incomplete" not in edge.data

    def test_missing_confidence_is_defaulted_to_medium_and_flagged(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            rationale="some rationale",
            source_span="some span",
        )
        assert edge.confidence == "MEDIUM"
        assert edge.data.get("confidence_missing") is True

    def test_explicit_confidence_is_preserved(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            rationale="some rationale",
            source_span="some span",
            confidence="LOW",
        )
        assert edge.confidence == "LOW"
        assert "confidence_missing" not in edge.data

    def test_explicit_none_confidence_is_defaulted_to_medium(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            rationale="some rationale",
            source_span="some span",
            confidence=None,
        )
        assert edge.confidence == "MEDIUM"
        assert edge.data.get("confidence_missing") is True

    def test_missing_confidence_in_json_is_defaulted_to_medium(self) -> None:
        payload = json.dumps(
            {
                "id": "e1",
                "source": "n1",
                "target": "n2",
                "label": "SUPPORTS",
                "type": "SUPPORTS",
                "rationale": "rationale",
                "source_span": "span",
            }
        )
        edge = ExtractedEdge.model_validate_json(payload)
        assert edge.confidence == "MEDIUM"
        assert edge.data.get("confidence_missing") is True

    def test_invalid_confidence_value_raises(self) -> None:
        with pytest.raises(ValueError):
            ExtractedEdge(
                id="e1",
                source="n1",
                target="n2",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="some rationale",
                source_span="some span",
                confidence="MAYBE",  # type: ignore[arg-type]
            )

    def test_non_core_edge_missing_confidence_is_flagged(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="USES_METHOD",
            type="USES_METHOD",
        )
        assert edge.confidence == "MEDIUM"
        assert edge.data.get("confidence_missing") is True
        assert "rationale_missing" not in edge.data

    def test_multiple_defects_are_all_recorded(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
        )
        assert edge.confidence == "MEDIUM"
        assert edge.data.get("confidence_missing") is True
        assert edge.data.get("rationale_missing") is True
        assert edge.data.get("incomplete") is True

    def test_existing_data_is_preserved_when_backfilling_confidence(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            rationale="some rationale",
            source_span="some span",
            data={"custom": 42},
        )
        assert edge.confidence == "MEDIUM"
        assert edge.data.get("custom") == 42
        assert edge.data.get("confidence_missing") is True

    def test_non_core_edge_missing_fields_is_not_flagged(self) -> None:
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="USES_METHOD",
            type="USES_METHOD",
        )
        assert "rationale_missing" not in edge.data
        assert "incomplete" not in edge.data

    def test_rationale_truncation_is_applied(self) -> None:
        long_rationale = "R" * 600
        edge = ExtractedEdge(
            id="e1",
            source="n1",
            target="n2",
            label="SUPPORTS",
            type="SUPPORTS",
            rationale=long_rationale,
            source_span="span",
        )
        assert edge.rationale.endswith("...")
        assert len(edge.rationale) == 500


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

    def test_invalid_edge_type_format_in_graph_raises(self) -> None:
        with pytest.raises(ValueError, match="Forbidden edge types"):
            ExtractedGraph(
                paper_id="paper-001",
                paradigm=Paradigm.HSS,
                nodes=[_hss_node()],
                edges=[_hss_edge(type="InvalidType")],
            )

    def test_graph_with_missing_confidence_edge_is_accepted(self) -> None:
        graph = ExtractedGraph(
            paper_id="paper-001",
            paradigm=Paradigm.HSS,
            nodes=[_hss_node()],
            edges=[_hss_edge(confidence=None)],  # type: ignore[call-arg]
        )
        assert graph.edges[0].confidence == "MEDIUM"
        assert graph.edges[0].data.get("confidence_missing") is True
