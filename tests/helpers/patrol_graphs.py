# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

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
    "build_hss_graph_with_method",
    "build_hss_graph_with_question_claim",
    "build_hss_graph_with_thesis",
    "build_hss_graph_without_lens",
    "build_hss_graph_without_thesis",
    "build_stem_graph_dataset_only",
    "build_stem_graph_with_method_dataset",
    "build_stem_graph_with_method_dataset_rq",
    "build_pca_mnist_synonym_golden_corpus",
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
    method_data: dict | None = None,
    dataset_id: str = "n_dataset",
    dataset_label: str,
    dataset_data: dict | None = None,
) -> UnifiedPaperGraph:
    """STEM graph with Method and Dataset nodes for method_overlap tests."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id=method_id, label=method_label, type=NodeType.METHOD, data=method_data or {}),
            GraphNode(id=dataset_id, label=dataset_label, type=NodeType.DATASET, data=dataset_data or {}),
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


def build_pca_mnist_synonym_golden_corpus() -> tuple[dict[str, UnifiedPaperGraph], tuple[str, str]]:
    """Golden STEM corpus for Plan C functional verification.

    Paper A uses label ``PCA``; paper B uses ``Principal Component Analysis``.
    Both methods share the normalized dataset label ``MNIST`` via EVALUATED_ON edges.
    """
    shared_dataset = "MNIST"
    paper_a_id = "stem-golden-a"
    paper_b_id = "stem-golden-b"
    graphs = {
        paper_a_id: build_stem_graph_with_method_dataset(
            paper_a_id,
            method_id="n_method_pca",
            method_label="PCA",
            method_data={
                "description": "Principal-component linear projection for digit images",
                "usage": "Applied PCA to MNIST pixel vectors before k-NN classification",
            },
            dataset_id="n_dataset_mnist_a",
            dataset_label=shared_dataset,
            dataset_data={"description": "28x28 handwritten digit benchmark"},
        ),
        paper_b_id: build_stem_graph_with_method_dataset(
            paper_b_id,
            method_id="n_method_pca_full",
            method_label="Principal Component Analysis",
            method_data={
                "description": "Orthogonal basis projection retaining top eigen-directions",
                "usage": "Principal Component Analysis compressed MNIST features to 50 dimensions",
            },
            dataset_id="n_dataset_mnist_b",
            dataset_label=shared_dataset,
            dataset_data={"description": "28x28 handwritten digit benchmark"},
        ),
    }
    return graphs, (paper_a_id, paper_b_id)


def build_stem_graph_with_method_dataset_rq(
    paper_id: str,
    *,
    method_id: str = "n_method",
    method_label: str,
    method_data: dict | None = None,
    dataset_id: str = "n_dataset",
    dataset_label: str,
    dataset_data: dict | None = None,
    question_id: str = "n_question",
    question_label: str,
    question_data: dict | None = None,
) -> UnifiedPaperGraph:
    """STEM graph with Method, Dataset, and ResearchQuestion wired for topology resonance tests."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[
            GraphNode(id=method_id, label=method_label, type=NodeType.METHOD, data=method_data or {}),
            GraphNode(id=dataset_id, label=dataset_label, type=NodeType.DATASET, data=dataset_data or {}),
            GraphNode(
                id=question_id,
                label=question_label,
                type=NodeType.RESEARCH_QUESTION,
                data=question_data or {},
            ),
        ],
        edges=[
            GraphEdge(
                id="e_evaluated_on",
                source=dataset_id,
                target=method_id,
                label="EVALUATED_ON",
                type="EVALUATED_ON",
            ),
            GraphEdge(
                id="e_addresses",
                source=method_id,
                target=question_id,
                label="ADDRESSES",
                type="ADDRESSES",
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


def build_hss_graph_with_method(
    paper_id: str,
    *,
    method_id: str = "n_method",
    method_label: str,
    method_data: dict | None = None,
) -> UnifiedPaperGraph:
    """HSS graph that still contains a Method node to test paradigm gate."""
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id=method_id, label=method_label, type=NodeType.METHOD, data=method_data or {}),
        ],
        edges=[],
    )


def build_stem_graph_dataset_only(
    paper_id: str,
    *,
    method_id: str = "n_method",
    method_label: str,
    dataset_id: str = "n_dataset",
    dataset_label: str,
    dataset_data: dict | None = None,
) -> UnifiedPaperGraph:
    """STEM graph with a method node and a dataset node.

    The default helper wires the dataset to the method.  To test dataset-only
    overlap, callers should construct two graphs whose method labels differ but
    whose dataset labels match.
    """
    return build_stem_graph_with_method_dataset(
        paper_id,
        method_id=method_id,
        method_label=method_label,
        dataset_id=dataset_id,
        dataset_label=dataset_label,
        dataset_data=dataset_data,
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
