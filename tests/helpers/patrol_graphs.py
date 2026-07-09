"""Shared helpers for patrol tests."""

from __future__ import annotations

from backend.patrol.samples import (
    build_hss_graph_with_lens,
    seed_corpus_patrol_graphs,
    seed_patrol_graphs,
)
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

__all__ = [
    "build_hss_graph_with_lens",
    "build_hss_graph_with_question_claim",
    "build_hss_graph_with_thesis",
    "build_hss_graph_without_lens",
    "build_hss_graph_without_thesis",
    "build_stem_graph_with_method_dataset",
    "build_stem_graph_with_question_claim",
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


def build_stem_graph_with_method_dataset(
    paper_id: str,
    *,
    method_id: str = "n_method",
    method_label: str,
    dataset_id: str = "n_dataset",
    dataset_label: str,
) -> UnifiedPaperGraph:
    """STEM graph with Method and Dataset nodes for method_overlap tests."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id=method_id, label=method_label, type=NodeType.METHOD, data={}),
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


def build_stem_graph_with_question_claim(
    paper_id: str,
    *,
    question_id: str = "n_question",
    question_label: str,
    claim_id: str = "n_claim",
    claim_label: str,
) -> UnifiedPaperGraph:
    """STEM graph with ResearchQuestion and Claim nodes for claim_evolution tests."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id=question_id, label=question_label, type=NodeType.RESEARCH_QUESTION, data={}),
            GraphNode(id=claim_id, label=claim_label, type=NodeType.CLAIM, data={}),
        ],
        edges=[
            GraphEdge(
                id="e_addresses",
                source=claim_id,
                target=question_id,
                label="ADDRESSES",
                type="ADDRESSES",
            ),
        ],
    )


def build_hss_graph_with_question_claim(
    paper_id: str,
    *,
    thesis_id: str = "n_thesis",
    thesis_label: str,
    claim_id: str = "n_claim",
    claim_label: str,
) -> UnifiedPaperGraph:
    """HSS graph with Thesis (as research question proxy) and Claim nodes for claim_evolution tests."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id=thesis_id, label=thesis_label, type=NodeType.THESIS, data={}),
            GraphNode(id=claim_id, label=claim_label, type=NodeType.CLAIM, data={}),
        ],
        edges=[
            GraphEdge(
                id="e_supports",
                source=claim_id,
                target=thesis_id,
                label="SUPPORTS",
                type="SUPPORTS",
            ),
        ],
    )
