"""Shared helpers for patrol tests."""

from __future__ import annotations

from backend.patrol.samples import (
    build_hss_graph_with_lens,
    seed_corpus_patrol_graphs,
    seed_patrol_graphs,
)
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

__all__ = [
    "build_hss_graph_with_lens",
    "build_hss_graph_with_thesis",
    "build_hss_graph_without_lens",
    "build_hss_graph_without_thesis",
    "seed_corpus_patrol_graphs",
    "seed_patrol_graphs",
]


def build_hss_graph_without_lens(paper_id: str) -> UnifiedPaperGraph:
    """HSS graph with Thesis but no AnalyticalLens (lens_clash insufficient-data)."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n_thesis", label="核心论点", type="Thesis", data={})],
        edges=[],
    )


def build_hss_graph_without_thesis(paper_id: str) -> UnifiedPaperGraph:
    """HSS graph with no Thesis nodes (for contradiction insufficient-data paths)."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n_lens", label="仅分析视角", type="AnalyticalLens", data={})],
        edges=[],
    )


def build_hss_graph_with_thesis(
    paper_id: str,
    *,
    thesis_id: str,
    thesis_label: str,
    sub_arguments: list[tuple[str, str]] | None = None,
) -> UnifiedPaperGraph:
    """HSS graph with Thesis (and optional SubArgument nodes) for contradiction tests."""
    nodes = [GraphNode(id=thesis_id, label=thesis_label, type="Thesis", data={})]
    edges = []
    for index, (sub_id, sub_label) in enumerate(sub_arguments or [], start=1):
        nodes.append(GraphNode(id=sub_id, label=sub_label, type="SubArgument", data={}))
        edges.append(
            GraphEdge(
                id=f"e_sub_{index}",
                source=sub_id,
                target=thesis_id,
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
        )
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=nodes,
        edges=edges,
    )
