"""Tests for second-order semantic clustering and island stitching."""

from __future__ import annotations

import pytest
from backend.config import Settings
from backend.graph.semantic_clustering import (
    _cross_type_merge_allowed,
    _deduplicate_edges_by_type,
    _elect_root,
    _node_text,
    semantic_cluster_and_merge,
)
from backend.schemas.extract_phase import (
    ExtractedEdge,
    ExtractedEdgeList,
    ExtractedGraph,
    ExtractedNode,
    ExtractedNodeList,
)
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
        prefix = "核心概念: "
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

    bridge = [e for e in result.edges if e.label == "semantically_related"]
    assert len(bridge) == 1
    assert bridge[0].type == "SEMANTICALLY_RELATED_TO"
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


class TestEdgeDeduplication:
    def test_deduplicate_edges_by_type_collapse_same_type_parallels(self) -> None:
        edges = [
            ExtractedEdge(id="e1", source="a", target="b", label="supports", type="SUPPORTS"),
            ExtractedEdge(id="e2", source="a", target="b", label="also supports", type="SUPPORTS"),
            ExtractedEdge(id="e3", source="a", target="b", label="contextualizes", type="CONTEXTUALIZES"),
        ]
        result = _deduplicate_edges_by_type(edges)
        assert len(result) == 2
        assert {e.type for e in result} == {"SUPPORTS", "CONTEXTUALIZES"}

    def test_deduplicate_edges_keeps_first_occurrence(self) -> None:
        edges = [
            ExtractedEdge(id="first", source="a", target="b", label="first", type="SUPPORTS"),
            ExtractedEdge(id="second", source="a", target="b", label="second", type="SUPPORTS"),
        ]
        result = _deduplicate_edges_by_type(edges)
        assert len(result) == 1
        assert result[0].id == "first"

    def test_deduplicate_edges_preserves_different_targets(self) -> None:
        edges = [
            ExtractedEdge(id="e1", source="a", target="b", label="supports", type="SUPPORTS"),
            ExtractedEdge(id="e2", source="a", target="c", label="supports", type="SUPPORTS"),
        ]
        result = _deduplicate_edges_by_type(edges)
        assert len(result) == 2


class TestNodeText:
    def test_includes_type_subtype_label_and_definition(self) -> None:
        node = ExtractedNode(
            id="n1",
            label="情感共鸣转向",
            type="Claim",
            sub_type="Argument",
            description="情感从个体转向集体共鸣的过程",
            source_span="这是一个非常长的原文片段，不应影响 embedding 输入" * 10,
        )
        text = _node_text(node)
        assert text.startswith("类型: Claim | 细分类别: Argument | 核心概念: 情感共鸣转向")
        assert "语义定义: 情感从个体转向集体共鸣的过程" in text
        assert "原文片段" not in text

    def test_falls_back_to_general_subtype_when_missing(self) -> None:
        node = ExtractedNode(
            id="n1",
            label="情感共鸣转向",
            type="Claim",
        )
        text = _node_text(node)
        assert "细分类别: General" in text
        assert "语义定义" not in text

    def test_reads_subtype_and_definition_from_data(self) -> None:
        node = ExtractedNode(
            id="n1",
            label="情感共鸣转向",
            type="Claim",
            data={"sub_type": "Cultural", "description": "defined in data"},
        )
        text = _node_text(node)
        assert "细分类别: Cultural" in text
        assert "语义定义: defined in data" in text


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
        _ = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.HSS,
            nodes=nodes.nodes,
            edges=edges.edges,
        )
        assert not _cross_type_merge_allowed("ObjectOrData", "Claim")

    def test_allowed_child_parent_merge_is_permitted(self) -> None:
        assert _cross_type_merge_allowed("SubArgument", "Claim")
        assert _cross_type_merge_allowed("ResearchQuestion", "Thesis")
        assert _cross_type_merge_allowed("Dataset", "Method")

    def test_evidence_is_isolated_from_claim_and_thesis(self) -> None:
        assert not _cross_type_merge_allowed("Evidence", "Claim")
        assert not _cross_type_merge_allowed("Evidence", "Thesis")
        assert not _cross_type_merge_allowed("Evidence", "Method")

    def test_central_types_cannot_absorb_each_other(self) -> None:
        assert not _cross_type_merge_allowed("Claim", "Thesis")
        assert not _cross_type_merge_allowed("Method", "Claim")
        assert not _cross_type_merge_allowed("AnalyticalLens", "Claim")
        assert not _cross_type_merge_allowed("IntellectualContext", "Thesis")

    def test_root_election_prefers_general_type(self) -> None:
        nodes = [
            ExtractedNode(id="sub1", label="Sub Arg", type="SubArgument", confidence=0.9),
            ExtractedNode(id="claim1", label="Main Claim", type="Claim", confidence=0.5),
        ]
        degrees = {"sub1": 10, "claim1": 1}
        nodes_by_id = {n.id: n for n in nodes}
        root = _elect_root({"sub1", "claim1"}, degrees, nodes_by_id)
        assert root == "claim1"

    def test_root_election_falls_back_to_degree(self) -> None:
        nodes = [
            ExtractedNode(id="claim1", label="Claim A", type="Claim", confidence=0.9),
            ExtractedNode(id="claim2", label="Claim B", type="Claim", confidence=0.5),
        ]
        degrees = {"claim1": 1, "claim2": 10}
        nodes_by_id = {n.id: n for n in nodes}
        root = _elect_root({"claim1", "claim2"}, degrees, nodes_by_id)
        assert root == "claim2"

        assert _cross_type_merge_allowed("Claim", "Claim")
        assert _cross_type_merge_allowed("Method", "Method")

    @pytest.mark.asyncio
    async def test_cross_type_penalty_tightens_merge_gate(self) -> None:
        """SubArgument-Claim at 0.87 raw similarity should NOT merge after -0.05 penalty."""

        from backend.graph.semantic_clustering import _node_text

        class _PenaltyEmbeddingClient:
            def __init__(self, vectors: dict[str, list[float]]) -> None:
                self._vectors = vectors

            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [self._vectors[t] for t in texts]

        # Low similarity pair: should remain separate.
        nodes_low = [
            ExtractedNode(id="sub_low", label="x", type="SubArgument"),
            ExtractedNode(id="claim_low", label="x", type="Claim"),
        ]
        texts_low = [_node_text(n) for n in nodes_low]
        vectors_low = dict(zip(texts_low, [[1.0, 0.0, 0.0], [0.87, 0.4931, 0.0]], strict=True))
        graph_low = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.HSS,
            nodes=nodes_low,
            edges=[],
        )
        result_low = await semantic_cluster_and_merge(
            graph_low, _settings(sim=0.85), embedding_client=_PenaltyEmbeddingClient(vectors_low)
        )
        assert len(result_low.nodes) == 2

        # High similarity pair: should merge.
        nodes_high = [
            ExtractedNode(id="sub_high", label="x", type="SubArgument"),
            ExtractedNode(id="claim_high", label="x", type="Claim"),
        ]
        texts_high = [_node_text(n) for n in nodes_high]
        vectors_high = dict(zip(texts_high, [[1.0, 0.0, 0.0], [0.95, 0.3122, 0.0]], strict=True))
        graph_high = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.HSS,
            nodes=nodes_high,
            edges=[],
        )
        result_high = await semantic_cluster_and_merge(
            graph_high, _settings(sim=0.85), embedding_client=_PenaltyEmbeddingClient(vectors_high)
        )
        assert len(result_high.nodes) == 1

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


class _OrthogonalEmbeddingClient:
    """Return one-hot vectors so every node is orthogonal (no similarity merges)."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        dim = max(len(texts), 8)
        return [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(len(texts))]


class TestEdgeRationaleMerging:
    def test_longer_rationale_wins_on_merge(self) -> None:
        from backend.graph.semantic_clustering import _merge_clusters

        nodes = [
            ExtractedNode(id="a", label="A", type="Method"),
            ExtractedNode(id="b", label="B", type="Method"),
            ExtractedNode(id="c", label="C", type="Method"),
        ]
        edges = [
            ExtractedEdge(
                id="e1",
                source="a",
                target="b",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="short",
                source_span="span1",
            ),
            ExtractedEdge(
                id="e2",
                source="a",
                target="b",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="this is the longer and more informative rationale",
                source_span="span2",
            ),
        ]
        merged_nodes, merged_edges, _, _ = _merge_clusters(
            nodes,
            edges,
            clusters=[{"a"}, {"b"}, {"c"}],
        )
        assert len(merged_edges) == 1
        assert merged_edges[0].rationale == "this is the longer and more informative rationale"

    def test_source_span_tie_breaks_when_rationale_equal(self) -> None:
        from backend.graph.semantic_clustering import _merge_clusters

        nodes = [
            ExtractedNode(id="a", label="A", type="Method"),
            ExtractedNode(id="b", label="B", type="Method"),
        ]
        edges = [
            ExtractedEdge(
                id="e1",
                source="a",
                target="b",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="same rationale",
                source_span="short",
            ),
            ExtractedEdge(
                id="e2",
                source="a",
                target="b",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="same rationale",
                source_span="this is a much longer source span that should win",
            ),
        ]
        _, merged_edges, _, _ = _merge_clusters(nodes, edges, clusters=[{"a"}, {"b"}])
        assert len(merged_edges) == 1
        assert "much longer source span" in (merged_edges[0].source_span or "")


class TestEdgeIdUniqueness:
    @pytest.mark.asyncio
    async def test_no_duplicate_edge_ids_after_self_loop_gaps_and_knn_bridges(self) -> None:
        """Regression: dropped self-loops used to leave id gaps; KNN bridges could collide."""
        nodes = [
            ExtractedNode(id="a", label="A", type="Method"),
            ExtractedNode(id="b", label="B", type="Method"),
            ExtractedNode(id="c", label="C", type="Method"),
            ExtractedNode(id="d", label="D", type="Method"),
            ExtractedNode(id="e", label="E", type="Method"),
            ExtractedNode(id="f", label="F", type="Method"),
            ExtractedNode(id="g", label="G", type="Method"),
            ExtractedNode(id="h", label="H", type="Method"),
        ]
        edges = [
            ExtractedEdge(id="e1", source="a", target="b", label="RELATES_TO", type="RELATES_TO"),
            ExtractedEdge(id="e2", source="c", target="c", label="RELATES_TO", type="RELATES_TO"),
            ExtractedEdge(id="e3", source="d", target="d", label="RELATES_TO", type="RELATES_TO"),
            ExtractedEdge(id="e4", source="e", target="f", label="RELATES_TO", type="RELATES_TO"),
            ExtractedEdge(id="e5", source="g", target="h", label="RELATES_TO", type="RELATES_TO"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=edges,
        )
        settings = Settings(
            _env_file=None,
            llm_mode="mock",
            semantic_clustering_enabled=True,
            semantic_similarity_threshold=1.0,
            semantic_knn_threshold=0.0,
        )
        result = await semantic_cluster_and_merge(
            graph,
            settings,
            embedding_client=_OrthogonalEmbeddingClient(),
        )
        edge_ids = [edge.id for edge in result.edges]
        assert len(edge_ids) == len(set(edge_ids))
        # All output edges should be valid UnifiedPaperGraph material.
        assert all(edge.id.startswith("e") for edge in result.edges)
