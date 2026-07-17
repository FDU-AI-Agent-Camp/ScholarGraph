# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Validation helpers for graph schemas."""

from backend.schemas.graph import HSS_NODE_TYPES, STEM_NODE_TYPES, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def ensure_graph_matches_paradigm(graph: UnifiedPaperGraph) -> UnifiedPaperGraph:
    """Return the graph if all nodes satisfy the graph paradigm, otherwise raise ValueError."""

    allowed = HSS_NODE_TYPES if graph.paradigm == Paradigm.HSS else STEM_NODE_TYPES
    forbidden = [node.type for node in graph.nodes if node.type not in allowed]
    if forbidden:
        raise ValueError(f"{graph.paradigm} graph contains forbidden node types: {forbidden}")
    return graph
