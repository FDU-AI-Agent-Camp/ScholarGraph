"""Schema validation tests for BE-2 graph contracts."""

from __future__ import annotations

import pytest
from backend.schemas import GraphEdge, GraphNode, NodeType, Paradigm, UnifiedPaperGraph


def test_rejects_forbidden_hss_node_type() -> None:
    with pytest.raises(ValueError, match="forbidden node types"):
        UnifiedPaperGraph(
            paper_id="p1",
            title="bad graph",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n_metric", label="Accuracy", type=NodeType.METRIC)],
            edges=[],
        )


def test_rejects_dangling_edge() -> None:
    with pytest.raises(ValueError, match="references missing node"):
        UnifiedPaperGraph(
            paper_id="p1",
            title="bad graph",
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n_method", label="Method", type=NodeType.METHOD)],
            edges=[
                GraphEdge(
                    id="e1",
                    source="n_method",
                    target="missing",
                    label="ADDRESSES",
                    type="ADDRESSES",
                )
            ],
        )


def test_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        UnifiedPaperGraph(
            paper_id="p1",
            title="bad graph",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n1", label="Thesis", type=NodeType.THESIS),
                GraphNode(id="n1", label="Sub", type=NodeType.SUB_ARGUMENT),
            ],
            edges=[],
        )
