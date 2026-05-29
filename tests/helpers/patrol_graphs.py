"""Shared helpers for patrol tests."""

from __future__ import annotations

from pathlib import Path

from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def build_hss_graph_with_lens(
    paper_id: str,
    *,
    lens_id: str,
    lens_label: str,
) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n_thesis", label="核心论点", type="Thesis", data={}),
            GraphNode(id=lens_id, label=lens_label, type="AnalyticalLens", data={}),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source=lens_id,
                target="n_thesis",
                label="LENS_OF",
                type="LENS_OF",
            ),
        ],
    )


def build_hss_graph_without_lens(paper_id: str) -> UnifiedPaperGraph:
    """HSS graph with no AnalyticalLens nodes (for insufficient-data paths)."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n_thesis", label="核心论点", type="Thesis", data={})],
        edges=[],
    )


def seed_patrol_graphs(store_dir: Path, paper_lens: dict[str, tuple[str, str]]) -> GraphStore:
    """Persist graphs with analytical lenses for patrol integration tests."""
    store = GraphStore(base_dir=store_dir)
    for paper_id, (lens_id, lens_label) in paper_lens.items():
        graph = build_hss_graph_with_lens(
            paper_id,
            lens_id=lens_id,
            lens_label=lens_label,
        )
        store.save(graph)
    return store
