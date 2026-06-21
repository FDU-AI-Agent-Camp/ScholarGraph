"""Graph quality gate for the extraction finalize step (Plan D).

A graph is flagged as low-confidence when:
- SUPPORTS rationale coverage < configured threshold, or
- isolated node ratio > configured threshold.

These checks run after extraction succeeds and before marking the paper ready.
"""

from __future__ import annotations

from backend.schemas.graph import GraphEdge, UnifiedPaperGraph


def supports_rationale_coverage(graph: UnifiedPaperGraph) -> float:
    """Fraction of SUPPORTS edges that carry a non-empty rationale."""
    supports_edges = [e for e in graph.edges if e.type == "SUPPORTS"]
    if not supports_edges:
        return 1.0

    def _has_rationale(edge: GraphEdge) -> bool:
        return bool(edge.rationale and edge.rationale.strip())

    covered = sum(1 for e in supports_edges if _has_rationale(e))
    return covered / len(supports_edges)


def isolated_node_ratio(graph: UnifiedPaperGraph) -> float:
    """Fraction of nodes with no incident edges."""
    if not graph.nodes:
        return 0.0
    connected_ids = set()
    for edge in graph.edges:
        connected_ids.add(edge.source)
        connected_ids.add(edge.target)
    isolated = sum(1 for node in graph.nodes if node.id not in connected_ids)
    return isolated / len(graph.nodes)


def evaluate_graph_quality(
    graph: UnifiedPaperGraph,
    *,
    min_supports_rationale_coverage: float,
    max_isolated_node_ratio: float,
) -> tuple[bool, list[str]]:
    """Return (passed, reasons) for the quality gate.

    ``reasons`` is empty when the graph passes; otherwise it contains
    human-readable strings describing the violated thresholds.
    """
    reasons: list[str] = []
    rationale_coverage = supports_rationale_coverage(graph)
    if rationale_coverage < min_supports_rationale_coverage:
        reasons.append(
            f"SUPPORTS rationale coverage {rationale_coverage:.1%} "
            f"below threshold {min_supports_rationale_coverage:.1%}",
        )

    isolated_ratio = isolated_node_ratio(graph)
    if isolated_ratio > max_isolated_node_ratio:
        reasons.append(
            f"isolated node ratio {isolated_ratio:.1%} above threshold {max_isolated_node_ratio:.1%}",
        )

    return not reasons, reasons
