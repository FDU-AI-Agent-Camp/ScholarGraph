"""Demo / eval graph seeds for patrol (see docs/v1/eval/patrol_samples.md)."""

from __future__ import annotations

from pathlib import Path

from backend.graph.store import GraphStore
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

CORPUS_HSS_PAPER_IDS: tuple[str, str] = ("hss-001", "hss-002")
CORPUS_STEM_PAPER_IDS: tuple[str, str] = ("stem-001", "stem-002")

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
            GraphNode(id="n_thesis", label="核心论点", type=NodeType.THESIS, data={}),
            GraphNode(id=lens_id, label=lens_label, type=NodeType.ANALYTICAL_LENS, data={}),
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


def build_stem_method_overlap_demo_graph(
    paper_id: str,
    *,
    method_id: str,
    method_label: str,
    dataset_id: str,
    dataset_label: str,
    method_data: dict | None = None,
) -> UnifiedPaperGraph:
    """STEM graph for method_overlap demo (PCA synonym pair on MNIST)."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id=method_id, label=method_label, type=NodeType.METHOD, data=method_data or {}),
            GraphNode(id=dataset_id, label=dataset_label, type=NodeType.DATASET, data={}),
        ],
        edges=[
            GraphEdge(
                id="e_evaluated_on",
                source=dataset_id,
                target=method_id,
                label="EVALUATED_ON",
                type="EVALUATED_ON",
            ),
        ],
    )


def build_stem_claim_evolution_demo_graph(
    paper_id: str,
    *,
    question_label: str,
    claim_label: str,
) -> UnifiedPaperGraph:
    """STEM graph for claim_evolution demo (aligned research questions)."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id="n_question", label=question_label, type=NodeType.RESEARCH_QUESTION, data={}),
            GraphNode(id="n_claim", label=claim_label, type=NodeType.CLAIM, data={}),
        ],
        edges=[
            GraphEdge(
                id="e_addresses",
                source="n_claim",
                target="n_question",
                label="ADDRESSES",
                type="ADDRESSES",
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


def seed_stem_patrol_graphs(store_dir: Path) -> GraphStore:
    """Write STEM micro-corpus for method_overlap / claim_evolution demo."""
    store = GraphStore(base_dir=store_dir)
    left_id, right_id = CORPUS_STEM_PAPER_IDS
    store.save(
        build_stem_method_overlap_demo_graph(
            left_id,
            method_id="n_method_pca",
            method_label="PCA",
            dataset_id="n_dataset_mnist_a",
            dataset_label="MNIST",
            method_data={
                "description": "Principal-component linear projection for digit images",
                "usage": "Applied PCA to MNIST pixel vectors before k-NN classification",
            },
        )
    )
    store.save(
        build_stem_method_overlap_demo_graph(
            right_id,
            method_id="n_method_pca_full",
            method_label="Principal Component Analysis",
            dataset_id="n_dataset_mnist_b",
            dataset_label="MNIST",
            method_data={
                "description": "Orthogonal basis projection retaining top eigen-directions",
                "usage": "Principal Component Analysis compressed MNIST features to 50 dimensions",
            },
        )
    )
    # Overwrite with claim_evolution-aligned RQ nodes while keeping method/dataset for overlap.
    for paper_id, claim_label in (
        (left_id, "PCA 将 MNIST 特征压缩至 50 维后分类准确率提升 3%"),
        (right_id, "主成分分析在 MNIST 上保留 95% 方差，分类性能与基线相当"),
    ):
        graph = store.load(paper_id)
        if graph is None:
            continue
        graph.nodes.append(
            GraphNode(
                id="n_question",
                label="PCA 是否提升 MNIST 分类准确率？",
                type=NodeType.RESEARCH_QUESTION,
                data={},
            )
        )
        graph.nodes.append(GraphNode(id="n_claim", label=claim_label, type=NodeType.CLAIM, data={}))
        graph.edges.append(
            GraphEdge(
                id="e_claim_question",
                source="n_claim",
                target="n_question",
                label="ADDRESSES",
                type="ADDRESSES",
            )
        )
        store.save(graph)
    return store
