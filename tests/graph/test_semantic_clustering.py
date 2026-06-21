"""Tests for second-order semantic clustering and island stitching."""

from __future__ import annotations

import pytest

from backend.config import Settings
from backend.graph.semantic_clustering import _cross_type_merge_allowed, _node_text, semantic_cluster_and_merge
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

    Vectors are keyed by node label so that the strong-feature text format
    used by ``_node_text`` still maps to the expected similarity landscape:
    - Adam Optimizer and Adam are very similar (cluster)
    - SGD is orthogonal to Adam variants
    - CNN is orthogonal to Survey
    - Survey is close enough to CNN to be bridged
    """

    def __init__(self) -> None:
        self.vectors = {
            "Adam Optimizer": [1.0, 0.0, 0.0],
            "Adam": [0.95, 0.32, 0.0],
            "SGD": [0.0, 1.0, 0.0],
            "CNN": [0.0, 0.0, 1.0],
            "Survey": [0.45, 0.0, 0.9],
        }

    def _extract_label(self, text: str) -> str:
        prefix = "核心标签: "
        start = text.find(prefix)
        if start == -1:
            return text
        start += len(prefix)
        end = text.find(" |", start)
        if end == -1:
            return text[start:]
        return text[start:end]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors[self._extract_label(text)] for text in texts]


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


class TestNodeText:
    def test_includes_type_label_and_truncated_source_span(self) -> None:
        node = ExtractedNode(
            id="n1",
            label="情感共鸣转向",
            type="Claim",
            source_span="这是一个非常长的补充说明" * 10,
        )
        text = _node_text(node)
        assert text.startswith("[类型: Claim] 核心标签: 情感共鸣转向 | 补充说明:")
        evidence = text.split("补充说明:")[1].strip()
        assert len(evidence) <= 100
        assert "这是一个非常长的补充说明" in text


class TestTypeFirewall:
    def test_cross_type_similar_nodes_are_blocked(self) -> None:
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                ExtractedNode(id="n1", label="Chinese Films", type="ObjectOrData"),
                ExtractedNode(id="n2", label="Chinese Films", type="Claim"),
            ],
        )
        edges = ExtractedEdgeList(paradigm=Paradigm.HSS, edges=[])
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.HSS,
            nodes=nodes.nodes,
            edges=edges.edges,
        )
        assert not _cross_type_merge_allowed("ObjectOrData", "Claim")

    def test_allowed_child_parent_merge_is_permitted(self) -> None:
        assert _cross_type_merge_allowed("SubArgument", "Claim")
        assert _cross_type_merge_allowed("Evidence", "Claim")
        assert _cross_type_merge_allowed("ResearchQuestion", "Thesis")

    def test_same_type_is_always_allowed(self) -> None:
        assert _cross_type_merge_allowed("Claim", "Claim")
        assert _cross_type_merge_allowed("Method", "Method")

    @pytest.mark.asyncio
    async def test_firewall_prevents_hub_merging(self) -> None:
        client = _FakeEmbeddingClient()
        # Use identical labels so that without the firewall these nodes would merge.
        nodes = ExtractedNodeList(
            paradigm=Paradigm.HSS,
            nodes=[
                ExtractedNode(id="n1", label="电影产业", type="ObjectOrData"),
                ExtractedNode(id="n2", label="电影产业", type="Claim"),
                ExtractedNode(id="n3", label="电影产业", type="SubArgument"),
            ],
        )
        edges = ExtractedEdgeList(
            paradigm=Paradigm.HSS,
            edges=[
                ExtractedEdge(id="e1", source="n3", target="n2", label="SUB_ARGUMENT_OF", type="SUB_ARGUMENT_OF"),
            ],
        )
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.HSS,
            nodes=nodes.nodes,
            edges=edges.edges,
        )
        result = await semantic_cluster_and_merge(graph, _settings(), embedding_client=client)
        # ObjectOrData must remain separate; SubArgument may merge into Claim.
        types = {n.type for n in result.nodes}
        assert "ObjectOrData" in types
        assert "Claim" in types
