"""Shared helpers for patrol tests."""

from __future__ import annotations

from backend.patrol.samples import (
    build_hss_graph_with_lens,
    seed_corpus_patrol_graphs,
    seed_patrol_graphs,
)
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

__all__ = [
    "build_hss_graph_with_lens",
    "build_hss_graph_without_lens",
    "seed_corpus_patrol_graphs",
    "seed_patrol_graphs",
]


def build_hss_graph_without_lens(paper_id: str) -> UnifiedPaperGraph:
    """HSS graph with no AnalyticalLens nodes (for insufficient-data paths)."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n_thesis", label="核心论点", type="Thesis", data={})],
        edges=[],
    )
