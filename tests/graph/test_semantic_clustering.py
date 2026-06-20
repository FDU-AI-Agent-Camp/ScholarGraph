"""Tests for second-order semantic clustering and island stitching."""

from __future__ import annotations

import pytest

from backend.config import Settings
from backend.graph.semantic_clustering import semantic_cluster_and_merge
from backend.schemas.extract_phase import ExtractedEdge, ExtractedEdgeList, ExtractedGraph, ExtractedNode, ExtractedNodeList
from backend.schemas.paradigm import Paradigm


def _graph() -> ExtractedGraph:
    """Return a small graph with two synonym clusters and one isolated island."""
    nodes = [
        ExtractedNode(id="n1", label="Adam Optimizer", type="Method"),
        ExtractedNode(id="n2", label="Adam", type="Method"),
        ExtractedNode(id="n3", label="SGD", type="Method"),
        ExtractedNode(id="n4", label="CNN", type="Method"),
        ExtractedNode(id="n5", label="Survey", type="Dataset"),
    ]
    edges = [
        ExtractedEdge(id="e1", source="n1", target="n4", label="uses", type="USES_METHOD"),
        ExtractedEdge(id="e2", source="n3", target="n4", label="uses", type="USES_METHOD"),
    ]
    return ExtractedGraph(
        paper_id="p1",
        title="Test",
        paradigm=Paradigm.STEM,
        nodes=nodes,
        edges=edges,
    )


class _FakeEmbeddingClient:
    """Deterministic embedding client for unit tests.

    Vectors are crafted so that:
    - n1 and n2 are identical (cluster)
    - n3 is orthogonal to n1/n2
    - n4 is orthogonal to n5
    - n5 is close enough to n4 to be bridged
    """

    def __init__(self) -> None:
        self.vectors = {
            "Adam Optimizer": [1.0, 0.0, 0.0],
            "Adam": [0.95, 0.32, 0.0],
            "SGD": [0.0, 1.0, 0.0],
            "CNN": [0.0, 0.0, 1.0],
            "Survey": [0.45, 0.0, 0.9],
        }

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors[text] for text in texts]


def _settings(enabled: bool = True, sim: float = 0.92, knn: float = 0.85) -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        semantic_clustering_enabled=enabled,
        semantic_similarity_threshold=sim,
        semantic_knn_threshold=knn,
    )


@pytest.mark.asyncio
async def test_merges_synonym_nodes_and_redirects_edges() -> None:
    graph = _graph()
    result = await semantic_cluster_and_merge(
        graph,
        _settings(),
        embedding_client=_FakeEmbeddingClient(),
    )

    labels = {n.label for n in result.nodes}
    assert "Adam Optimizer" in labels or "Adam" in labels
    assert len(result.nodes) == 4  # Adam merged + SGD + CNN + Survey
    assert any("SEMANTIC_CLUSTERS_MERGED:1" in w for w in result.warnings)

    # Edge from n1 should now originate from the elected root.
    adam_edges = [e for e in result.edges if e.source in ("n1", "n2") or e.target in ("n1", "n2")]
    assert len(adam_edges) <= 1


@pytest.mark.asyncio
async def test_does_not_merge_dissimilar_nodes() -> None:
    graph = _graph()
    result = await semantic_cluster_and_merge(
        graph,
        _settings(sim=0.99),
        embedding_client=_FakeEmbeddingClient(),
    )

    assert len(result.nodes) == 5
    assert not any("SEMANTIC_CLUSTERS_MERGED" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_adds_knn_bridge_from_island_to_main_component() -> None:
    graph = _graph()
    result = await semantic_cluster_and_merge(
        graph,
        _settings(),
        embedding_client=_FakeEmbeddingClient(),
    )

    bridge = [e for e in result.edges if e.label == "semantic_related"]
    assert len(bridge) == 1
    assert bridge[0].type == "RELATES_TO"
    assert any("SEMANTIC_KNN_EDGES_ADDED:1" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_disabled_clustering_returns_graph_unchanged() -> None:
    graph = _graph()
    result = await semantic_cluster_and_merge(
        graph,
        _settings(enabled=False),
        embedding_client=_FakeEmbeddingClient(),
    )

    assert len(result.nodes) == 5
    assert len(result.edges) == 2
    assert not any("SEMANTIC" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_embedding_failure_is_graceful() -> None:
    class _FailingClient:
        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embedding service down")

    graph = _graph()
    result = await semantic_cluster_and_merge(
        graph,
        _settings(),
        embedding_client=_FailingClient(),
    )

    assert len(result.nodes) == 5
    assert any("SEMANTIC_CLUSTERING_SKIPPED" in w for w in result.warnings)
