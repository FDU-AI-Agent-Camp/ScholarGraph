"""Phase F.3 schema unit tests: STEM node/edge whitelist on UnifiedPaperGraph."""

from __future__ import annotations

import pytest
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from pydantic import ValidationError
from tests.helpers.f33_stem_graphs import (
    F33_FORBIDDEN_HSS_NODE_TYPES,
    assert_stem_excludes_hss_only_node_types,
    assert_stem_schema_whitelist,
    minimal_f33_stem_graph,
)


def test_f33_minimal_stem_graph_passes_schema() -> None:
    graph = minimal_f33_stem_graph()
    assert_stem_schema_whitelist(graph)
    assert len(graph.nodes) >= 7
    assert len(graph.edges) >= 5


@pytest.mark.parametrize("hss_only_type", sorted(F33_FORBIDDEN_HSS_NODE_TYPES))
def test_f33_stem_graph_rejects_each_hss_only_node_type(hss_only_type: str) -> None:
    with pytest.raises(ValidationError, match="forbidden node types"):
        UnifiedPaperGraph(
            paper_id=f"bad-stem-{hss_only_type}",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(id="n_hss", label="hss node", type=hss_only_type),
                GraphNode(id="n_method", label="方法", type=NodeType.METHOD),
            ],
            edges=[
                GraphEdge(id="e1", source="n_method", target="n_hss", label="RELATES_TO", type="RELATES_TO"),
            ],
        )


def test_f33_minimal_stem_graph_excludes_hss_only_node_types() -> None:
    assert_stem_excludes_hss_only_node_types(minimal_f33_stem_graph())


def test_f33_stem_graph_accepts_dynamic_hss_edge_type() -> None:
    """Dynamic relation invention allows uppercase SNAKE_CASE edge types across paradigms."""
    base = minimal_f33_stem_graph()
    graph = UnifiedPaperGraph(
        paper_id=base.paper_id,
        paradigm=Paradigm.STEM,
        nodes=base.nodes,
        edges=[
            *base.edges,
            GraphEdge(
                id="e_bad",
                source="n_method",
                target="n_question",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
        ],
    )
    assert graph.edges[-1].type == "SUB_ARGUMENT_OF"


def test_f33_stem_graph_rejects_supported_by_inverse_edge() -> None:
    """SUPPORTED_BY was removed from the STEM ontology; only Evidence->Claim SUPPORTS is allowed."""
    base = minimal_f33_stem_graph()
    with pytest.raises(ValidationError, match="forbidden edge types"):
        UnifiedPaperGraph(
            paper_id=base.paper_id,
            paradigm=Paradigm.STEM,
            nodes=base.nodes,
            edges=[
                *base.edges,
                GraphEdge(
                    id="e_bad",
                    source="n_claim",
                    target="n_evidence",
                    label="SUPPORTED_BY",
                    type="SUPPORTED_BY",
                ),
            ],
        )


def test_f33_stem_graph_accepts_optional_experiment_finding() -> None:
    graph = UnifiedPaperGraph(
        paper_id="stem-exp",
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="n_question", label="任务", type=NodeType.RESEARCH_QUESTION),
            GraphNode(id="n_method", label="方法", type=NodeType.METHOD),
            GraphNode(id="n_exp", label="消融实验", type=NodeType.EXPERIMENT),
            GraphNode(id="n_finding", label="发现", type=NodeType.FINDING),
        ],
        edges=[
            GraphEdge(id="e1", source="n_method", target="n_question", label="ADDRESSES", type="ADDRESSES"),
            GraphEdge(id="e2", source="n_exp", target="n_finding", label="PRODUCES", type="PRODUCES"),
        ],
    )
    assert_stem_schema_whitelist(graph)
