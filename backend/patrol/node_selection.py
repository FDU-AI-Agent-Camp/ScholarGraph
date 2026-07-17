# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Deterministic primary-node selection for patrol analysers."""

from __future__ import annotations

from backend.schemas.graph import GraphNode, UnifiedPaperGraph

_RICHNESS_KEYS = ("description", "text", "usage")


def _node_has_rich_text(node: GraphNode) -> bool:
    data = node.data or {}
    return any(isinstance(data.get(key), str) and data[key].strip() for key in _RICHNESS_KEYS)


def _node_edge_count(node: GraphNode, graph: UnifiedPaperGraph | None) -> int:
    if graph is None:
        return 0
    return sum(1 for edge in graph.edges if edge.source == node.id or edge.target == node.id)


def _node_rank_key(node: GraphNode, graph: UnifiedPaperGraph | None) -> tuple[int, int, int, str]:
    """Lower tuple values are preferred when using ``min``."""
    return (
        0 if _node_has_rich_text(node) else 1,
        -_node_edge_count(node, graph),
        -len(node.label.strip()),
        node.id,
    )


def select_primary_node(
    nodes: list[GraphNode],
    *,
    graph: UnifiedPaperGraph | None = None,
) -> GraphNode | None:
    """Pick the most representative node using metadata richness, not list order.

    Priority:
    1. Nodes with non-empty description/text/usage metadata.
    2. Nodes with more graph edges.
    3. Longer labels (usually more informative).
    4. Stable tie-break by ``node.id``.
    """
    if not nodes:
        return None
    if len(nodes) == 1:
        return nodes[0]
    return min(nodes, key=lambda node: _node_rank_key(node, graph))
