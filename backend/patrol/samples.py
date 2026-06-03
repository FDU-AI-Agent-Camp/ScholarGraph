"""Demo / eval graph seeds for patrol (see docs/v1/eval/patrol_samples.md)."""

from __future__ import annotations

from pathlib import Path

from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

CORPUS_HSS_PAPER_IDS: tuple[str, str] = ("hss-001", "hss-002")

CORPUS_PATROL_LENSES: dict[str, tuple[str, str]] = {
    "hss-001": ("n_lens_molecular_history", "分子考古与民族史视角"),
    "hss-002": ("n_lens_political_film", "政治传播与电影叙事"),
}


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


def seed_patrol_graphs(store_dir: Path, paper_lens: dict[str, tuple[str, str]]) -> GraphStore:
    store = GraphStore(base_dir=store_dir)
    for paper_id, (lens_id, lens_label) in paper_lens.items():
        store.save(
            build_hss_graph_with_lens(
                paper_id,
                lens_id=lens_id,
                lens_label=lens_label,
            )
        )
    return store


def seed_corpus_patrol_graphs(store_dir: Path) -> GraphStore:
    """Write HSS micro-corpus graphs for patrol smoke / eval."""
    return seed_patrol_graphs(store_dir, CORPUS_PATROL_LENSES)
