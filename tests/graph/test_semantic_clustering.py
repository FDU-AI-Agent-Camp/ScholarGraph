"""Tests for second-order semantic clustering and island stitching."""

from __future__ import annotations

import numpy as np
import pytest
from backend.config import Settings
from backend.graph.semantic_clustering import (
    _coarse_filter_pairs,
    _cross_type_merge_allowed,
    _deduplicate_edges_by_type,
    _elect_root,
    _fuse_descriptions,
    _group_nodes_by_type,
    _merge_clusters,
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


def _settings(
    enabled: bool = True,
    sim: float = 0.92,
    knn: float = 0.85,
    dynamic_thresholds: bool = False,
) -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        semantic_clustering_enabled=enabled,
        semantic_similarity_threshold=sim,
        semantic_clustering_dynamic_thresholds_enabled=dynamic_thresholds,
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

    def test_same_type_merge_is_permitted(self) -> None:
        """The stage-1 firewall only allows comparisons within the exact same type."""
        assert _cross_type_merge_allowed("Claim", "Claim")
        assert _cross_type_merge_allowed("Method", "Method")
        assert _cross_type_merge_allowed("Dataset", "Dataset")
        assert not _cross_type_merge_allowed("SubArgument", "Claim")
        assert not _cross_type_merge_allowed("ResearchQuestion", "Thesis")
        assert not _cross_type_merge_allowed("Dataset", "Method")

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

    @pytest.mark.asyncio
    async def test_hard_type_firewall_blocks_identical_cross_type_labels(self) -> None:
        """Even with identical labels and high similarity, different types must not merge."""

        class _IdenticalEmbeddingClient:
            """Return the same vector for every text to simulate perfect similarity."""

            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        nodes = [
            ExtractedNode(id="n1", label="film industry", type="ObjectOrData"),
            ExtractedNode(id="n2", label="film industry", type="Claim"),
            ExtractedNode(id="n3", label="film industry", type="SubArgument"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.HSS,
            nodes=nodes,
            edges=[],
        )
        result = await semantic_cluster_and_merge(
            graph,
            _settings(sim=0.5),
            embedding_client=_IdenticalEmbeddingClient(),
        )
        assert len(result.nodes) == 3
        assert not any("SEMANTIC_CLUSTERS_MERGED" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_same_type_high_similarity_still_merges(self) -> None:
        """The firewall must not break legitimate within-type synonym merging."""

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        nodes = [
            ExtractedNode(id="n1", label="Adam Optimizer", type="Method"),
            ExtractedNode(id="n2", label="Adam", type="Method"),
            ExtractedNode(id="n3", label="SGD", type="Method"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )
        result = await semantic_cluster_and_merge(
            graph,
            _settings(sim=0.5),
            embedding_client=_IdenticalEmbeddingClient(),
        )
        assert len(result.nodes) == 1
        assert any("SEMANTIC_CLUSTERS_MERGED:1" in w for w in result.warnings)

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
        # Hard type firewall: every distinct type must survive.
        types = {n.type for n in result.nodes}
        assert types == {"ObjectOrData", "Claim", "SubArgument"}

    @pytest.mark.asyncio
    async def test_dynamic_threshold_method_stricter_than_dataset_in_stem(self) -> None:
        """STEM Method threshold (0.92) should block merges that Dataset threshold (0.82) allows."""

        class _TypedEmbeddingClient:
            def __init__(self, vectors: dict[str, list[float]]) -> None:
                self._vectors = vectors

            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [self._vectors[t] for t in texts]

        # Two Method nodes at 0.90 similarity: below STEM Method threshold 0.92.
        method_texts = [
            "类型: Method | 细分类别: General | 核心概念: Adam Optimizer",
            "类型: Method | 细分类别: General | 核心概念: Adam",
        ]
        method_vectors = dict(zip(method_texts, [[1.0, 0.0, 0.0], [0.90, 0.4359, 0.0]], strict=True))
        method_graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=[
                ExtractedNode(id="m1", label="Adam Optimizer", type="Method"),
                ExtractedNode(id="m2", label="Adam", type="Method"),
            ],
            edges=[],
        )
        result_method = await semantic_cluster_and_merge(
            method_graph,
            _settings(sim=-1.0, dynamic_thresholds=True),
            embedding_client=_TypedEmbeddingClient(method_vectors),
        )
        assert len(result_method.nodes) == 2, "STEM Method pair at 0.90 should not merge"

        # Two Dataset nodes at 0.85 similarity: above STEM Dataset threshold 0.82.
        dataset_texts = [
            "类型: Dataset | 细分类别: General | 核心概念: Fangzhi Yunnan",
            "类型: Dataset | 细分类别: General | 核心概念: Fangzhi Yunnan Data",
        ]
        dataset_vectors = dict(zip(dataset_texts, [[1.0, 0.0, 0.0], [0.85, 0.5268, 0.0]], strict=True))
        dataset_graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=[
                ExtractedNode(id="d1", label="Fangzhi Yunnan", type="Dataset"),
                ExtractedNode(id="d2", label="Fangzhi Yunnan Data", type="Dataset"),
            ],
            edges=[],
        )
        result_dataset = await semantic_cluster_and_merge(
            dataset_graph,
            _settings(sim=-1.0, dynamic_thresholds=True),
            embedding_client=_TypedEmbeddingClient(dataset_vectors),
        )
        assert len(result_dataset.nodes) == 1, "STEM Dataset pair at 0.85 should merge"

    @pytest.mark.asyncio
    async def test_explicit_similarity_threshold_overrides_dynamic_matrix(self) -> None:
        """When SEMANTIC_SIMILARITY_THRESHOLD is set explicitly, dynamic matrix is ignored."""

        class _TypedEmbeddingClient:
            def __init__(self, vectors: dict[str, list[float]]) -> None:
                self._vectors = vectors

            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [self._vectors[t] for t in texts]

        texts = [
            "类型: Method | 细分类别: General | 核心概念: Adam Optimizer",
            "类型: Method | 细分类别: General | 核心概念: Adam",
        ]
        vectors = dict(zip(texts, [[1.0, 0.0, 0.0], [0.90, 0.4359, 0.0]], strict=True))
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=[
                ExtractedNode(id="m1", label="Adam Optimizer", type="Method"),
                ExtractedNode(id="m2", label="Adam", type="Method"),
            ],
            edges=[],
        )
        # Explicit sim=0.85 is lower than STEM Method 0.92, so it should merge.
        result = await semantic_cluster_and_merge(
            graph,
            _settings(sim=0.85, dynamic_thresholds=True),
            embedding_client=_TypedEmbeddingClient(vectors),
        )
        assert len(result.nodes) == 1


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


class TestGroupNodesByType:
    def test_groups_by_type_and_preserves_indices(self) -> None:
        nodes = [
            ExtractedNode(id="n1", label="Adam", type="Method"),
            ExtractedNode(id="n2", label="CNN", type="Method"),
            ExtractedNode(id="n3", label="IMDb", type="Dataset"),
            ExtractedNode(id="n4", label="Survey", type="Dataset"),
        ]
        groups = _group_nodes_by_type(nodes)
        assert set(groups.keys()) == {"Method", "Dataset"}
        assert groups["Method"] == [(0, nodes[0]), (1, nodes[1])]
        assert groups["Dataset"] == [(2, nodes[2]), (3, nodes[3])]

    def test_empty_nodes_returns_empty_groups(self) -> None:
        assert _group_nodes_by_type([]) == {}

    def test_single_node_group(self) -> None:
        nodes = [ExtractedNode(id="n1", label="Adam", type="Method")]
        groups = _group_nodes_by_type(nodes)
        assert groups == {"Method": [(0, nodes[0])]}


class TestCoarseFilterPairs:
    def _nodes(self, count: int) -> list[ExtractedNode]:
        return [
            ExtractedNode(id=f"n{i}", label=f"node {i}", type="Method")
            for i in range(count)
        ]

    def test_returns_pairs_above_threshold(self) -> None:
        nodes = self._nodes(3)
        # Three orthogonal unit vectors; only (0, 1) is close.
        embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.95, 0.31, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )
        pairs = _coarse_filter_pairs(nodes, embeddings, threshold=0.90)
        assert len(pairs) == 1
        assert pairs[0][0] == "n0"
        assert pairs[0][1] == "n1"
        assert pairs[0][2] > 0.90

    def test_excludes_self_pairs_and_duplicates(self) -> None:
        nodes = self._nodes(3)
        embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        pairs = _coarse_filter_pairs(nodes, embeddings, threshold=0.99)
        # Only (0,1), (0,2), (1,2); no (i,i) and no (j,i).
        assert len(pairs) == 3
        pair_ids = {(a, b) for a, b, _ in pairs}
        assert pair_ids == {("n0", "n1"), ("n0", "n2"), ("n1", "n2")}

    def test_threshold_boundary_is_exclusive(self) -> None:
        nodes = self._nodes(2)
        embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.90, 0.4359, 0.0],  # cosine ~= 0.90
            ],
            dtype=np.float32,
        )
        # score > 0.90 (strict) should yield zero pairs.
        assert _coarse_filter_pairs(nodes, embeddings, threshold=0.90) == []
        # score > 0.89 should yield one pair.
        pairs = _coarse_filter_pairs(nodes, embeddings, threshold=0.89)
        assert len(pairs) == 1

    def test_zero_vectors_produce_no_pairs(self) -> None:
        nodes = self._nodes(2)
        embeddings = np.zeros((2, 4), dtype=np.float32)
        pairs = _coarse_filter_pairs(nodes, embeddings, threshold=0.0)
        assert pairs == []

    def test_empty_and_single_node_inputs(self) -> None:
        assert _coarse_filter_pairs([], np.zeros((0, 4)), threshold=0.0) == []
        node = self._nodes(1)
        assert _coarse_filter_pairs(node, np.zeros((1, 4)), threshold=0.0) == []

    def test_l2_normalization_matches_cosine(self) -> None:
        """Un-normalized input vectors must still produce cosine scores."""
        nodes = self._nodes(2)
        # Same direction, different magnitudes.
        embeddings = np.array(
            [
                [2.0, 0.0, 0.0],
                [5.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        pairs = _coarse_filter_pairs(nodes, embeddings, threshold=0.99)
        assert len(pairs) == 1
        assert pairs[0][2] == pytest.approx(1.0, abs=1e-6)

    def test_mismatched_embedding_count_returns_empty(self) -> None:
        nodes = self._nodes(2)
        embeddings = np.zeros((3, 4), dtype=np.float32)
        assert _coarse_filter_pairs(nodes, embeddings, threshold=0.0) == []

    @pytest.mark.asyncio
    async def test_integration_matrix_filter_matches_legacy_loop(self) -> None:
        """The NumPy coarse-filter must produce the same merges as the old loop."""

        class _MatrixEmbeddingClient:
            """Vectors keyed by label so the matrix filter can exercise grouping."""

            vectors = {
                "Adam Optimizer": [1.0, 0.0, 0.0],
                "Adam": [0.95, 0.32, 0.0],
                "SGD": [0.0, 1.0, 0.0],
                "CNN": [0.0, 0.0, 1.0],
                "Survey": [0.45, 0.0, 0.9],
            }

            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                prefix = "核心概念: "
                result = []
                for text in texts:
                    start = text.find(prefix) + len(prefix)
                    end = text.find(" |", start)
                    label = text[start:end] if end != -1 else text[start:]
                    result.append(self.vectors[label])
                return result

        graph = _graph()
        result = await semantic_cluster_and_merge(
            graph,
            _settings(),
            embedding_client=_MatrixEmbeddingClient(),
        )
        labels = {n.label for n in result.nodes}
        assert "Adam Optimizer" in labels or "Adam" in labels
        assert len(result.nodes) == 4
        assert any("SEMANTIC_CLUSTERS_MERGED:1" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_all_distinct_types_produce_no_merge_pairs(self) -> None:
        """When every node has a different type, the matrix filter is never invoked."""

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        nodes = [
            ExtractedNode(id="n1", label="x", type="Method"),
            ExtractedNode(id="n2", label="x", type="Dataset"),
            ExtractedNode(id="n3", label="x", type="Claim"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )
        result = await semantic_cluster_and_merge(
            graph,
            _settings(sim=0.5),
            embedding_client=_IdenticalEmbeddingClient(),
        )
        assert len(result.nodes) == 3
        assert not any("SEMANTIC_CLUSTERS_MERGED" in w for w in result.warnings)


class _MockRerankerClient:
    """Deterministic reranker scores keyed by (text_a, text_b) tuples."""

    def __init__(self, scores: dict[tuple[str, str], float]) -> None:
        self._scores = scores

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self._scores.get(pair, 0.5) for pair in pairs]


class TestRerankerFineFilter:
    def _rerank_settings(
        self,
        enabled: bool = True,
        threshold: float = 0.85,
        sim: float = 0.5,
    ) -> Settings:
        return Settings(
            _env_file=None,
            llm_mode="mock",
            semantic_clustering_enabled=True,
            semantic_similarity_threshold=sim,
            reranker_enabled=enabled,
            reranker_model="bge-reranker-v2-m3",
            reranker_api_base_url="https://api.example.com/v1",
            reranker_api_key="fake-key",
            reranker_threshold=threshold,
        )

    @pytest.mark.asyncio
    async def test_reranker_blocks_false_synonyms(self) -> None:
        """数学分析 vs 内容分析 should be rejected by the reranker fine-filter."""

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        nodes = [
            ExtractedNode(id="n1", label="数学分析", type="Method"),
            ExtractedNode(id="n2", label="内容分析", type="Method"),
            ExtractedNode(id="n3", label="PCA", type="Method"),
            ExtractedNode(id="n4", label="Principal Component Analysis", type="Method"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )

        reranker = _MockRerankerClient(
            {
                (_node_text(nodes[0]), _node_text(nodes[1])): 0.30,  # 数学分析 vs 内容分析
                (_node_text(nodes[0]), _node_text(nodes[2])): 0.30,
                (_node_text(nodes[0]), _node_text(nodes[3])): 0.30,
                (_node_text(nodes[1]), _node_text(nodes[2])): 0.30,
                (_node_text(nodes[1]), _node_text(nodes[3])): 0.30,
                (_node_text(nodes[2]), _node_text(nodes[3])): 0.95,  # PCA synonym
            }
        )

        result = await semantic_cluster_and_merge(
            graph,
            self._rerank_settings(),
            embedding_client=_IdenticalEmbeddingClient(),
            reranker_client=reranker,
        )

        labels = {n.label for n in result.nodes}
        assert "PCA" in labels or "Principal Component Analysis" in labels
        assert "数学分析" in labels
        assert "内容分析" in labels
        assert len(result.nodes) == 3
        assert any("SEMANTIC_CLUSTERS_MERGED:1" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_reranker_accepts_true_synonyms(self) -> None:
        """Two phrasings of the same concept should pass the reranker and merge."""

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        nodes = [
            ExtractedNode(id="n1", label="PCA", type="Method"),
            ExtractedNode(id="n2", label="Principal Component Analysis", type="Method"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )

        reranker = _MockRerankerClient(
            {(_node_text(nodes[0]), _node_text(nodes[1])): 0.95}
        )

        result = await semantic_cluster_and_merge(
            graph,
            self._rerank_settings(),
            embedding_client=_IdenticalEmbeddingClient(),
            reranker_client=reranker,
        )

        assert len(result.nodes) == 1
        assert any("SEMANTIC_CLUSTERS_MERGED:1" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_reranker_failure_skips_merging(self) -> None:
        """If the reranker raises, clustering is skipped and a warning is emitted."""

        class _FailingRerankerClient:
            async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
                raise RuntimeError("reranker unavailable")

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        nodes = [
            ExtractedNode(id="n1", label="PCA", type="Method"),
            ExtractedNode(id="n2", label="Principal Component Analysis", type="Method"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )

        result = await semantic_cluster_and_merge(
            graph,
            self._rerank_settings(),
            embedding_client=_IdenticalEmbeddingClient(),
            reranker_client=_FailingRerankerClient(),
        )

        assert len(result.nodes) == 2
        assert any("SEMANTIC_CLUSTERING_RERANK_SKIPPED" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_disabled_reranker_uses_coarse_filter_only(self) -> None:
        """When reranker is disabled, coarse-filter pairs pass through unchanged.

        This is a fidelity-degraded fallback and emits a strong warning log.
        The RerankerClient itself no longer returns 1.0 when disabled;
        semantic_cluster_and_merge simply bypasses the fine-filter stage.
        """

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        nodes = [
            ExtractedNode(id="n1", label="数学分析", type="Method"),
            ExtractedNode(id="n2", label="内容分析", type="Method"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )

        result = await semantic_cluster_and_merge(
            graph,
            self._rerank_settings(enabled=False),
            embedding_client=_IdenticalEmbeddingClient(),
        )

        assert len(result.nodes) == 1
        assert any("SEMANTIC_CLUSTERS_MERGED:1" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_reranker_input_is_normalized_by_node_id(self) -> None:
        """Asymmetric reranker must always receive (smaller_id, larger_id) order."""

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        class _AsymmetricRerankerClient:
            def __init__(self) -> None:
                self.observed_pairs: list[tuple[str, str]] = []

            async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
                self.observed_pairs.extend(pairs)
                scores = []
                for text_a, _text_b in pairs:
                    # The stable direction (smaller id as query) scores high;
                    # the reversed direction scores low.
                    if "类型: Method | 细分类别: General | 核心概念: Adam" in text_a:
                        scores.append(0.95)
                    else:
                        scores.append(0.30)
                return scores

        # Deliberately create ids where the first node has a larger id than the
        # second, so the coarse-filter could return them in either order.
        nodes = [
            ExtractedNode(id="z_adam", label="Adam Optimizer", type="Method"),
            ExtractedNode(id="a_adam", label="Adam", type="Method"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )
        reranker = _AsymmetricRerankerClient()

        result = await semantic_cluster_and_merge(
            graph,
            self._rerank_settings(),
            embedding_client=_IdenticalEmbeddingClient(),
            reranker_client=reranker,
        )

        assert len(result.nodes) == 1
        assert len(reranker.observed_pairs) == 1
        text_a, _text_b = reranker.observed_pairs[0]
        # a_adam has the smaller id, so its text must be the query.
        assert "核心概念: Adam" in text_a
        assert "核心概念: Adam Optimizer" not in text_a


class TestDescriptionFusion:
    def test_fuse_descriptions_deduplicates_and_joins(self) -> None:
        result = _fuse_descriptions(["desc A", "desc B", "desc A"])
        assert result == "desc A | desc B"

    def test_fuse_descriptions_single_returns_unchanged(self) -> None:
        assert _fuse_descriptions(["only one"]) == "only one"

    def test_fuse_descriptions_empty_returns_empty(self) -> None:
        assert _fuse_descriptions([]) == ""
        assert _fuse_descriptions(["", "  "]) == ""

    def test_merge_clusters_fuses_descriptions_into_root(self) -> None:
        nodes = [
            ExtractedNode(id="a", label="A", type="Method", description="Root description"),
            ExtractedNode(id="b", label="B", type="Method", description="Alias description one"),
            ExtractedNode(id="c", label="C", type="Method", description="Alias description two"),
        ]
        merged_nodes, _, _, _ = _merge_clusters(nodes, [], clusters=[{"a", "b", "c"}])
        assert len(merged_nodes) == 1
        root = merged_nodes[0]
        assert "Root description" in (root.description or "")
        assert "Alias description one" in (root.description or "")
        assert "Alias description two" in (root.description or "")

    def test_merge_clusters_keeps_original_description_for_singleton(self) -> None:
        nodes = [
            ExtractedNode(id="a", label="A", type="Method", description="Singleton description"),
        ]
        merged_nodes, _, _, _ = _merge_clusters(nodes, [], clusters=[{"a"}])
        assert len(merged_nodes) == 1
        assert merged_nodes[0].description == "Singleton description"

    def test_merge_clusters_tolerates_missing_descriptions(self) -> None:
        nodes = [
            ExtractedNode(id="a", label="A", type="Method"),
            ExtractedNode(id="b", label="B", type="Method", description="Only this"),
        ]
        merged_nodes, _, _, _ = _merge_clusters(nodes, [], clusters=[{"a", "b"}])
        assert len(merged_nodes) == 1
        assert merged_nodes[0].description == "Only this"


class TestUnionFindTransitivity:
    @pytest.mark.asyncio
    async def test_transitive_pairs_merge_into_single_cluster(self) -> None:
        """A~B and B~C through reranker should merge A, B, C into one node."""

        class _IdenticalEmbeddingClient:
            async def embed_texts(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0] for _ in texts]

        class _TransitiveRerankerClient:
            async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
                return [0.95] * len(pairs)

        nodes = [
            ExtractedNode(id="n1", label="Adam", type="Method"),
            ExtractedNode(id="n2", label="Adam Optimizer", type="Method"),
            ExtractedNode(id="n3", label="Adaptive Moment Estimation", type="Method"),
        ]
        graph = ExtractedGraph(
            paper_id="p1",
            title="T",
            paradigm=Paradigm.STEM,
            nodes=nodes,
            edges=[],
        )
        result = await semantic_cluster_and_merge(
            graph,
            Settings(
                _env_file=None,
                llm_mode="mock",
                semantic_clustering_enabled=True,
                semantic_similarity_threshold=0.5,
                reranker_enabled=True,
                reranker_model="bge-reranker-v2-m3",
                reranker_api_base_url="https://api.example.com/v1",
                reranker_api_key="fake-key",
                reranker_threshold=0.85,
            ),
            embedding_client=_IdenticalEmbeddingClient(),
            reranker_client=_TransitiveRerankerClient(),
        )
        assert len(result.nodes) == 1
        root = result.nodes[0]
        assert len(root.data.get("semantic_aliases", [])) == 2
        assert any("SEMANTIC_CLUSTERS_MERGED:1" in w for w in result.warnings)
