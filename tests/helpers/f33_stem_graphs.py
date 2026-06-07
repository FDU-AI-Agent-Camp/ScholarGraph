"""F.3 STEM verification-chain graph builders and assertions for tests."""

from __future__ import annotations

from backend.schemas.graph import (
    STEM_EDGE_TYPES,
    STEM_NODE_TYPES,
    GraphEdge,
    GraphNode,
    NodeType,
    UnifiedPaperGraph,
)
from backend.schemas.paradigm import Paradigm

F33_STEM_CORE_EDGE_TYPES = frozenset(
    {
        "ADDRESSES",
        "EVALUATED_ON",
        "MEASURED_BY",
        "COMPARES_TO",
        "SUPPORTS",
    },
)


def minimal_f33_stem_graph(*, paper_id: str = "f33-stem") -> UnifiedPaperGraph:
    """Schema-valid STEM graph matching F.3 minimum viable structure."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="n_question", label="研究问题", type=NodeType.RESEARCH_QUESTION),
            GraphNode(id="n_method", label="Transformer 方法", type=NodeType.METHOD),
            GraphNode(id="n_dataset", label="GLUE benchmark", type=NodeType.DATASET),
            GraphNode(id="n_metric", label="F1 分数", type=NodeType.METRIC),
            GraphNode(id="n_baseline", label="BERT 基线", type=NodeType.BASELINE),
            GraphNode(id="n_claim", label="优于 SOTA", type=NodeType.CLAIM),
            GraphNode(id="n_evidence", label="实验表 2 结果", type=NodeType.EVIDENCE),
        ],
        edges=[
            GraphEdge(
                id="e_addresses",
                source="n_method",
                target="n_question",
                label="ADDRESSES",
                type="ADDRESSES",
            ),
            GraphEdge(
                id="e_evaluated",
                source="n_method",
                target="n_dataset",
                label="EVALUATED_ON",
                type="EVALUATED_ON",
            ),
            GraphEdge(
                id="e_measured",
                source="n_claim",
                target="n_metric",
                label="MEASURED_BY",
                type="MEASURED_BY",
            ),
            GraphEdge(
                id="e_compares",
                source="n_claim",
                target="n_baseline",
                label="COMPARES_TO",
                type="COMPARES_TO",
            ),
            GraphEdge(
                id="e_supports",
                source="n_evidence",
                target="n_claim",
                label="SUPPORTS",
                type="SUPPORTS",
            ),
        ],
        summary="F.3 STEM test fixture",
    )


def assert_stem_schema_whitelist(graph: UnifiedPaperGraph) -> None:
    node_types = {node.type for node in graph.nodes}
    edge_types = {edge.type for edge in graph.edges}
    assert node_types <= {t.value for t in STEM_NODE_TYPES}
    assert edge_types <= STEM_EDGE_TYPES


def assert_f33_stem_core_structure(graph: UnifiedPaperGraph) -> None:
    assert graph.paradigm == Paradigm.STEM
    types = [node.type for node in graph.nodes]
    assert types.count(NodeType.RESEARCH_QUESTION) == 1
    assert NodeType.METHOD in types
    assert NodeType.METRIC in types
    assert NodeType.CLAIM in types
    assert NodeType.EVIDENCE in types
    assert any(edge.type == "ADDRESSES" for edge in graph.edges)
    assert any(edge.type == "SUPPORTS" for edge in graph.edges)
