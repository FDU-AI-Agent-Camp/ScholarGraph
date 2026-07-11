"""Unit tests for method_overlap topology resonance filter."""

from __future__ import annotations

import pytest
from backend.patrol.method_overlap_topology import (
    has_topology_resonance,
    one_hop_neighbors,
)
from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset_rq


class _FakeEmbeddingClient:
    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = {
            "Does PCA improve accuracy?": [1.0, 0.0],
            "Can PCA boost classifier performance?": [0.95, 0.31],
            "Unrelated question A": [0.0, 1.0],
            "Unrelated question B": [0.0, 0.9],
        }
        return [vectors.get(text, [0.0, 0.0]).copy() for text in texts]


def test_one_hop_neighbors_collects_dataset_and_question() -> None:
    graph = build_stem_graph_with_method_dataset_rq(
        "stem-001",
        method_label="PCA",
        dataset_label="MNIST",
        question_label="Does PCA improve accuracy?",
    )
    neighbors = one_hop_neighbors(graph, "n_method")
    labels = {node.label for node in neighbors}
    assert labels == {"MNIST", "Does PCA improve accuracy?"}


@pytest.mark.asyncio
async def test_has_topology_resonance_accepts_shared_dataset() -> None:
    left_graph = build_stem_graph_with_method_dataset_rq(
        "stem-001",
        method_label="PCA",
        dataset_label="MNIST",
        question_label="Question A",
    )
    right_graph = build_stem_graph_with_method_dataset_rq(
        "stem-002",
        method_label="Principal Component Analysis",
        dataset_label="MNIST",
        question_label="Question B",
    )
    assert await has_topology_resonance(
        left_graph,
        right_graph,
        left_graph.nodes[0],
        right_graph.nodes[0],
        embedding_client=_FakeEmbeddingClient(),
        rq_threshold=0.75,
    )


@pytest.mark.asyncio
async def test_has_topology_resonance_rejects_disjoint_neighborhoods() -> None:
    left_graph = build_stem_graph_with_method_dataset_rq(
        "stem-001",
        method_label="Naive Bayes",
        dataset_label="MNIST",
        question_label="Digits question",
    )
    right_graph = build_stem_graph_with_method_dataset_rq(
        "stem-002",
        method_label="Logistic Regression",
        dataset_label="CIFAR-10",
        question_label="Objects question",
    )
    assert not await has_topology_resonance(
        left_graph,
        right_graph,
        left_graph.nodes[0],
        right_graph.nodes[0],
        embedding_client=_FakeEmbeddingClient(),
        rq_threshold=0.75,
    )


@pytest.mark.asyncio
async def test_has_topology_resonance_accepts_semantically_similar_questions() -> None:
    left_graph = build_stem_graph_with_method_dataset_rq(
        "stem-001",
        method_label="PCA",
        dataset_label="Dataset A",
        question_label="Does PCA improve accuracy?",
    )
    right_graph = build_stem_graph_with_method_dataset_rq(
        "stem-002",
        method_label="Principal Component Analysis",
        dataset_label="Dataset B",
        question_label="Can PCA boost classifier performance?",
    )
    assert await has_topology_resonance(
        left_graph,
        right_graph,
        left_graph.nodes[0],
        right_graph.nodes[0],
        embedding_client=_FakeEmbeddingClient(),
        rq_threshold=0.75,
    )
