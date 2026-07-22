# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for extract_repair classification and prompt assembly."""

from __future__ import annotations

import pytest
from backend.agents.extract_repair import (
    build_extracted_graph,
    build_repair_prompt,
    classify_validation_error,
    format_error_messages,
)
from backend.schemas.extract_phase import ExtractedEdge, ExtractedEdgeList, ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm
from pydantic import ValidationError


def _node_validation_error(*, duplicate: bool = False, forbidden_type: bool = False) -> ValidationError:
    nodes = [
        ExtractedNode(id="n1", label="PCA", type="Method"),
        ExtractedNode(id="n1" if duplicate else "n2", label="SGD", type="BadType" if forbidden_type else "Method"),
    ]
    with pytest.raises(ValidationError) as exc_info:
        ExtractedNodeList(paradigm=Paradigm.STEM, nodes=nodes)
    return exc_info.value


def _edge_validation_error(*, forbidden_type: bool = False) -> ValidationError:
    payload = {
        "paradigm": Paradigm.STEM,
        "node_ids": ["n1", "n2"],
        "edges": [
            ExtractedEdge(
                id="e1",
                source="n1",
                target="n2",
                label="uses",
                type="SUPPORTED_BY" if forbidden_type else "USES_METHOD",
            ),
        ],
    }
    with pytest.raises(ValidationError) as exc_info:
        ExtractedEdgeList.model_validate(payload)
    return exc_info.value


def test_classify_validation_error_node_duplicate_ids() -> None:
    exc = _node_validation_error(duplicate=True)
    assert classify_validation_error(exc) == "nodes"


def test_classify_validation_error_node_forbidden_type() -> None:
    exc = _node_validation_error(forbidden_type=True)
    assert classify_validation_error(exc) == "nodes"


def test_classify_validation_error_edge_forbidden_type() -> None:
    exc = _edge_validation_error(forbidden_type=True)
    assert classify_validation_error(exc) == "edges"


def test_format_error_messages_lists_locations() -> None:
    exc = _node_validation_error(duplicate=True)
    formatted = format_error_messages(exc)
    assert formatted.startswith("- [")
    assert "]" in formatted


def test_build_repair_prompt_includes_paradigm_whitelist_and_scope() -> None:
    previous = ExtractedNodeList(
        paradigm=Paradigm.STEM,
        nodes=[ExtractedNode(id="n1", label="PCA", type="Method")],
    )
    prompt = build_repair_prompt(
        paradigm=Paradigm.STEM,
        error_messages="- [nodes.0.type] forbidden",
        previous_data=previous,
        level="nodes",
    )
    assert "PCA" in prompt
    assert "Method" in prompt
    assert "USES_METHOD" in prompt
    assert "STEM" in prompt or "stem" in prompt.lower()
    assert "nodes-level errors" in prompt


def test_build_repair_prompt_hss_edge_level() -> None:
    previous = ExtractedEdgeList(
        paradigm=Paradigm.HSS,
        node_ids=["n1", "n2"],
        edges=[
            ExtractedEdge(id="e1", source="n1", target="n2", label="supports", type="SUPPORTS"),
        ],
    )
    prompt = build_repair_prompt(
        paradigm=Paradigm.HSS,
        error_messages="- [edges.0.type] forbidden edge type",
        previous_data=previous,
        level="edges",
    )
    assert "Thesis" in prompt or "Claim" in prompt
    assert "edges-level errors" in prompt


def test_build_extracted_graph_validates_combined_graph() -> None:
    nodes = ExtractedNodeList(
        paradigm=Paradigm.STEM,
        nodes=[
            ExtractedNode(id="n1", label="PCA", type="Method"),
            ExtractedNode(id="n2", label="Dataset", type="Dataset"),
        ],
    )
    edges = ExtractedEdgeList(
        paradigm=Paradigm.STEM,
        node_ids=["n1", "n2"],
        edges=[
            ExtractedEdge(id="e1", source="n1", target="n2", label="uses", type="USES_METHOD"),
        ],
    )
    graph = build_extracted_graph("paper-001", "Title", Paradigm.STEM, nodes, edges, summary="ok")
    assert graph.paper_id == "paper-001"
    assert len(graph.nodes) == 2
    assert graph.edges[0].target == "n2"


def test_build_extracted_graph_raises_on_dangling_edge() -> None:
    nodes = ExtractedNodeList(
        paradigm=Paradigm.STEM,
        nodes=[ExtractedNode(id="n1", label="PCA", type="Method")],
    )
    dangling_edges = ExtractedEdgeList.model_construct(
        paradigm=Paradigm.STEM,
        node_ids=["n1"],
        edges=[
            ExtractedEdge(id="e1", source="n1", target="missing", label="uses", type="USES_METHOD"),
        ],
    )
    with pytest.raises(ValidationError):
        build_extracted_graph("paper-001", None, Paradigm.STEM, nodes, dangling_edges)
