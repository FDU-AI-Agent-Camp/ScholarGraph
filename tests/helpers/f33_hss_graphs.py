"""F.3 HSS argumentation-tree graph builders and assertions for tests."""

from __future__ import annotations

from backend.schemas.graph import (
    HSS_EDGE_TYPES,
    HSS_NODE_TYPES,
    STEM_NODE_TYPES,
    GraphEdge,
    GraphNode,
    NodeType,
    UnifiedPaperGraph,
)
from backend.schemas.paradigm import Paradigm

# STEM-only node types forbidden in HSS graphs (Claim/Evidence are shared).
F33_FORBIDDEN_STEM_NODE_TYPES = frozenset(node_type.value for node_type in (STEM_NODE_TYPES - HSS_NODE_TYPES))

F33_HSS_CORE_EDGE_TYPES = frozenset(
    {
        "SUB_ARGUMENT_OF",
        "CHALLENGES",
        "EXAMINES_THROUGH",
        "LENS_OF",
        "INFORMS",
        "SUPPORTS",
    },
)


def minimal_f33_hss_graph(*, paper_id: str = "f33-hss") -> UnifiedPaperGraph:
    """Schema-valid HSS graph matching F.3 minimum viable structure."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n_thesis", label="核心论点", type=NodeType.THESIS),
            GraphNode(id="n_sub_1", label="分论点一", type=NodeType.SUB_ARGUMENT),
            GraphNode(id="n_sub_2", label="分论点二", type=NodeType.SUB_ARGUMENT),
            GraphNode(id="n_sub_3", label="分论点三", type=NodeType.SUB_ARGUMENT),
            GraphNode(id="n_lens", label="历史制度主义", type=NodeType.ANALYTICAL_LENS),
            GraphNode(id="n_object", label="通商口岸档案", type=NodeType.OBJECT_OR_DATA),
            GraphNode(id="n_context", label="传统现代化叙事", type=NodeType.INTELLECTUAL_CONTEXT),
        ],
        edges=[
            GraphEdge(
                id="e_sub_1",
                source="n_sub_1",
                target="n_thesis",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
            GraphEdge(
                id="e_sub_2",
                source="n_sub_2",
                target="n_thesis",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
            GraphEdge(
                id="e_sub_3",
                source="n_sub_3",
                target="n_thesis",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
            GraphEdge(
                id="e_object_lens",
                source="n_object",
                target="n_lens",
                label="EXAMINES_THROUGH",
                type="EXAMINES_THROUGH",
            ),
            GraphEdge(
                id="e_lens_thesis",
                source="n_lens",
                target="n_thesis",
                label="LENS_OF",
                type="LENS_OF",
            ),
            GraphEdge(
                id="e_thesis_context",
                source="n_thesis",
                target="n_context",
                label="CHALLENGES",
                type="CHALLENGES",
            ),
        ],
        summary="F.3 test fixture",
    )


def assert_hss_schema_whitelist(graph: UnifiedPaperGraph) -> None:
    node_types = {node.type for node in graph.nodes}
    edge_types = {edge.type for edge in graph.edges}
    assert node_types <= {t.value for t in HSS_NODE_TYPES}
    assert edge_types <= HSS_EDGE_TYPES
    assert_hss_excludes_stem_only_node_types(graph)


def assert_hss_excludes_stem_only_node_types(graph: UnifiedPaperGraph) -> None:
    """F.3: HSS graphs must not contain Metric, Baseline, Dataset, etc."""
    node_types = {node.type for node in graph.nodes}
    forbidden = node_types & F33_FORBIDDEN_STEM_NODE_TYPES
    assert not forbidden, f"HSS graph contains forbidden STEM-only types: {sorted(forbidden)}"


def assert_f33_core_structure(graph: UnifiedPaperGraph, *, min_sub_arguments: int = 3) -> None:
    """Assert F.3 argumentation-tree shape (counts are prompt targets, not schema hard limits)."""
    assert graph.paradigm == Paradigm.HSS
    types = [node.type for node in graph.nodes]
    assert types.count(NodeType.THESIS) == 1
    assert sum(1 for node_type in types if node_type == NodeType.SUB_ARGUMENT) >= min_sub_arguments
    assert NodeType.ANALYTICAL_LENS in types
    assert NodeType.OBJECT_OR_DATA in types
    assert any(edge.type == "SUB_ARGUMENT_OF" for edge in graph.edges)
    assert any(edge.type == "EXAMINES_THROUGH" for edge in graph.edges)
