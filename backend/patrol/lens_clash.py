"""Lens Clash patrol logic (BE-4)."""

from collections.abc import Mapping

from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.patrol import NodeRef, PatrolInsight

ANALYTICAL_LENS_NODE_TYPE = "AnalyticalLens"
LENS_CLASH_INSIGHT_ID = "ins-lens-clash-001"
LENS_CLASH_TITLE = "理论视角冲突（Lens Clash）"


def analytical_lens_nodes(graph: UnifiedPaperGraph) -> list[GraphNode]:
    """Return AnalyticalLens nodes from a unified paper graph."""
    return [node for node in graph.nodes if node.type == ANALYTICAL_LENS_NODE_TYPE]


def build_lens_clash_insight(
    graphs: Mapping[str, UnifiedPaperGraph],
    paper_ids: list[str],
) -> PatrolInsight | None:
    """Compare primary analytical lenses across two papers and build one insight."""
    if len(paper_ids) != 2:
        return None

    left_id, right_id = paper_ids
    left_lens = _primary_lens(graphs.get(left_id))
    right_lens = _primary_lens(graphs.get(right_id))
    if left_lens is None or right_lens is None:
        return None

    summary = _build_lens_clash_summary(left_lens.label, right_lens.label)
    return PatrolInsight(
        insight_id=LENS_CLASH_INSIGHT_ID,
        title=LENS_CLASH_TITLE,
        summary=summary,
        paper_ids=[left_id, right_id],
        node_refs=[
            NodeRef(paper_id=left_id, node_id=left_lens.id, label=left_lens.label),
            NodeRef(paper_id=right_id, node_id=right_lens.id, label=right_lens.label),
        ],
    )


def _primary_lens(graph: UnifiedPaperGraph | None) -> GraphNode | None:
    if graph is None:
        return None
    lenses = analytical_lens_nodes(graph)
    if not lenses:
        return None
    return lenses[0]


def _build_lens_clash_summary(left_label: str, right_label: str) -> str:
    if left_label == right_label:
        return f"两篇论文均采用「{left_label}」作为分析视角，当前图谱中未检出显著学派冲突。"
    return (
        f"两篇论文分别采用「{left_label}」与「{right_label}」作为分析视角，"
        "理论框架存在潜在学派冲突，建议对照核心论点与分论点关系进一步研判。"
    )
