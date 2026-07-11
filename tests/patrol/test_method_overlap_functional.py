"""Functional verification for method_overlap Plan C topology resonance.

These tests exercise production modules end-to-end (semantic finder, topology
filter, context assembly, alignment merger) with a golden STEM corpus.  Only the
LLM boundary is stubbed to avoid live API calls.
"""

from __future__ import annotations

import logging
import math
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import get_settings
from backend.patrol.method_overlap import (
    _find_overlap_pairs,
    build_method_overlap_insight,
    method_nodes,
)
from backend.patrol.method_overlap_semantic import find_semantic_method_overlap
from backend.patrol.method_overlap_topology import has_topology_resonance, one_hop_neighbors
from backend.patrol.similarity import cosine_similarity, normalize_label
from backend.schemas.graph import GraphEdge, GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol import MethodOverlapPoint, OverlapType, PatrolInsightStatus
from backend.schemas.patrol_llm import MethodComparativeDetail, MethodOverlapOutput
from tests.helpers.patrol_graphs import (
    build_pca_mnist_synonym_golden_corpus,
    build_stem_graph_with_method_dataset_rq,
)
from tests.patrol.conftest import patch_patrol_settings

_METHOD_OVERLAP_LOGGER = "backend.patrol.method_overlap"
_GOLDEN_PAIR_LABEL = "PCA <-> Principal Component Analysis"
_GOLDEN_RAG_CHUNK_A = "On MNIST, PCA retained 95% variance with 50 principal components."
_GOLDEN_RAG_CHUNK_B = "Principal Component Analysis compressed MNIST digit features similarly."
_LIVE_NB_LR_COSINE = 0.82
_NB_CIRCUIT_BREAKER_VECTOR = [1.0, 0.0]
_LR_CIRCUIT_BREAKER_VECTOR = [_LIVE_NB_LR_COSINE, math.sqrt(1.0 - _LIVE_NB_LR_COSINE**2)]
_LIVE_NB_LR_NOISE_COSINE = 0.90
_NB_NOISE_VECTOR = [1.0, 0.0]
_LR_NOISE_VECTOR = [_LIVE_NB_LR_NOISE_COSINE, math.sqrt(1.0 - _LIVE_NB_LR_NOISE_COSINE**2)]


class _GoldenPcaEmbeddingClient:
    """Deterministic vectors for PCA ↔ Principal Component Analysis (not is_mock)."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: dict[str, list[float]] = {}
        for text in texts:
            if text.startswith("PCA") or text.startswith("PCA "):
                vectors[text] = [1.0, 0.0, 0.0]
            elif "Principal Component Analysis" in text:
                vectors[text] = [0.99, 0.01, 0.0]
            else:
                vectors[text] = [0.0, 0.0, 1.0]
        return [vectors.get(text, [0.0, 0.0, 0.0]).copy() for text in texts]


@pytest.fixture
def golden_pca_mnist_corpus() -> tuple[dict, tuple[str, str]]:
    return build_pca_mnist_synonym_golden_corpus()


@pytest.mark.asyncio
async def test_functional_topology_resonance_pca_synonym_golden_corpus_end_to_end(
    golden_pca_mnist_corpus: tuple[dict, tuple[str, str]],
) -> None:
    """Plan C functional verification: MNIST topology rescues PCA synonym pair through production stack."""
    graphs, paper_ids = golden_pca_mnist_corpus
    left_id, right_id = paper_ids
    settings = get_settings()

    assert settings.enable_patrol_semantic_path is True

    left_graph = graphs[left_id]
    right_graph = graphs[right_id]
    left_methods = method_nodes(left_graph)
    right_methods = method_nodes(right_graph)
    assert len(left_methods) == 1
    assert len(right_methods) == 1

    # Literal path must miss (synonym labels differ after normalization).
    literal_anchors = _find_overlap_pairs(left_methods, right_methods, OverlapType.METHOD)
    assert literal_anchors == []
    assert normalize_label(left_methods[0].label) != normalize_label(right_methods[0].label)

    embedding_client = _GoldenPcaEmbeddingClient()

    # Production topology filter: shared MNIST dataset neighbor must resonate.
    assert await has_topology_resonance(
        left_graph,
        right_graph,
        left_methods[0],
        right_methods[0],
        embedding_client=embedding_client,
        settings=settings,
    )

    # Production semantic finder: embedding pre-screen + topology gate.
    semantic_anchor = await find_semantic_method_overlap(
        left_graph,
        right_graph,
        left_methods,
        right_methods,
        embedding_client,
        settings.patrol_semantic_threshold,
        settings.patrol_max_matrix_size,
        settings=settings,
    )
    assert semantic_anchor is not None
    assert semantic_anchor.match_type == "semantic"
    assert semantic_anchor.overlap_score >= settings.patrol_semantic_threshold
    assert semantic_anchor.pair_label == _GOLDEN_PAIR_LABEL

    llm_output = MethodOverlapOutput(
        summary="两篇论文在 MNIST 上均通过主成分分析压缩图像特征后完成分类实验。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name=_GOLDEN_PAIR_LABEL,
                paper_a_usage="论文 A 在 MNIST 上使用 PCA 保留 95% 方差并降至 50 维后执行 k-NN。",
                paper_b_usage="论文 B 使用 Principal Component Analysis 将 MNIST 特征压缩至 48 维。",
                evidence_summary=(
                    "拓扑共振确认两篇论文共享 MNIST 实验场景；"
                    "PCA 与 Principal Component Analysis 在特征投影流程上高度一致。"
                ),
            ),
        ],
    )

    vector_store = AsyncMock()
    vector_store.exists.return_value = True
    vector_store.query_chunks.side_effect = [
        [AsyncMock(text=_GOLDEN_RAG_CHUNK_A)],
        [AsyncMock(text=_GOLDEN_RAG_CHUNK_B)],
    ]

    with patch(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        new_callable=AsyncMock,
        return_value=llm_output,
    ) as mock_summary:
        insight = await build_method_overlap_insight(
            graphs,
            list(paper_ids),
            vector_store=vector_store,
            embedding_client=embedding_client,
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.summary == llm_output.summary

    assert len(insight.structured_points) == 2
    method_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.METHOD)
    dataset_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.DATASET)
    assert isinstance(method_point, MethodOverlapPoint)
    assert method_point.mode == "method_overlap"
    assert method_point.overlap_type == OverlapType.METHOD
    assert method_point.match_type == "semantic"
    assert method_point.overlap_score is not None
    assert method_point.overlap_score >= settings.patrol_semantic_threshold
    assert method_point.method == "PCA"
    assert method_point.overlap_label == "PCA"
    assert method_point.paper_a_usage == llm_output.comparison_details[0].paper_a_usage
    assert method_point.paper_b_usage == llm_output.comparison_details[0].paper_b_usage
    assert method_point.evidence_summary == llm_output.comparison_details[0].evidence_summary
    assert "PCA" in method_point.paper_a_usage
    assert "Principal Component Analysis" in method_point.paper_b_usage
    assert "MNIST" in method_point.evidence_summary
    assert isinstance(dataset_point, MethodOverlapPoint)
    assert dataset_point.overlap_type == OverlapType.DATASET
    assert dataset_point.overlap_label == "MNIST"

    assert {ref.label for ref in method_point.node_refs} == {"PCA", "Principal Component Analysis"}
    assert {ref.label for ref in dataset_point.node_refs} == {"MNIST"}
    assert {ref.label for ref in insight.node_refs} == {"PCA", "Principal Component Analysis", "MNIST"}

    context = mock_summary.call_args.args[0]
    assert _GOLDEN_PAIR_LABEL in context
    assert "MNIST" in context
    assert _GOLDEN_RAG_CHUNK_A in context
    assert _GOLDEN_RAG_CHUNK_B in context
    assert left_id in context
    assert right_id in context
    vector_store.query_chunks.assert_awaited()

    pca_text = "PCA Principal-component linear projection for digit images"
    pca_full_text = "Principal Component Analysis Orthogonal basis projection retaining top eigen-directions"
    assert (
        cosine_similarity(
            (await embedding_client.embed_texts([pca_text]))[0],
            (await embedding_client.embed_texts([pca_full_text]))[0],
        )
        >= settings.patrol_semantic_threshold
    )


class _SpyEmbeddingClient:
    """Fails if production code invokes embedding while a short-circuit gate is active."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("EmbeddingClient.embed_texts must not be called when entry gate short-circuits")


class _NbLrHighSimilarityEmbeddingClient:
    """NB ↔ LR cosine ≈ 0.82 — would match if soft path were enabled."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "Naive Bayes" in text:
                vectors.append(_NB_CIRCUIT_BREAKER_VECTOR.copy())
            elif "Logistic Regression" in text:
                vectors.append(_LR_CIRCUIT_BREAKER_VECTOR.copy())
            else:
                vectors.append([0.0, 0.0])
        return vectors


@pytest.mark.asyncio
async def test_boundary_semantic_path_disabled_short_circuits_without_embedding(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """软通路硬熔断：ENABLE_PATROL_SEMANTIC_PATH=false 时短路，绝不调用 EmbeddingClient。"""
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=False, patrol_semantic_threshold=0.75)
    settings = get_settings()

    graphs = {
        "stem-soft-a": build_stem_graph_with_method_dataset_rq(
            "stem-soft-a",
            method_label="Naive Bayes",
            method_data={"description": "probabilistic generative classifier"},
            dataset_label="Dataset X",
            question_label="Can Naive Bayes classify images in dataset X?",
        ),
        "stem-soft-b": build_stem_graph_with_method_dataset_rq(
            "stem-soft-b",
            method_label="Logistic Regression",
            method_data={"description": "discriminative linear classifier"},
            dataset_label="Dataset Y",
            question_label="Does logistic regression improve accuracy on dataset Y?",
        ),
    }

    spy_client = _SpyEmbeddingClient()
    high_sim_client = _NbLrHighSimilarityEmbeddingClient()
    assert cosine_similarity(_NB_CIRCUIT_BREAKER_VECTOR, _LR_CIRCUIT_BREAKER_VECTOR) == pytest.approx(
        _LIVE_NB_LR_COSINE,
        abs=1e-6,
    )
    assert (
        cosine_similarity(_NB_CIRCUIT_BREAKER_VECTOR, _LR_CIRCUIT_BREAKER_VECTOR) >= settings.patrol_semantic_threshold
    )

    def _forbidden_get_embedding_client() -> _SpyEmbeddingClient:
        raise AssertionError("get_embedding_client must not be called when semantic path is disabled")

    monkeypatch.setattr("backend.patrol.method_overlap.get_embedding_client", _forbidden_get_embedding_client)

    with (
        caplog.at_level(logging.INFO, logger=_METHOD_OVERLAP_LOGGER),
        patch(
            "backend.patrol.method_overlap.find_semantic_method_overlap",
            side_effect=AssertionError("find_semantic_method_overlap must not be called"),
        ),
    ):
        insight = await build_method_overlap_insight(
            graphs,
            ["stem-soft-a", "stem-soft-b"],
            embedding_client=spy_client,
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []

    audit_records = [
        record for record in caplog.records if record.getMessage() == "skipped_due_to_semantic_path_disabled"
    ]
    assert len(audit_records) == 1
    assert audit_records[0].paper_ids == ["stem-soft-a", "stem-soft-b"]  # type: ignore[attr-defined]

    # Prove the spy would have fired; high-similarity client is never reached in production path.
    with pytest.raises(AssertionError, match="must not be called when entry gate short-circuits"):
        await spy_client.embed_texts(["Naive Bayes"])
    await high_sim_client.embed_texts(["Naive Bayes", "Logistic Regression"])


class _NbLrNoiseEmbeddingClient:
    """Live false-positive pair: NB ↔ LR cosine ≈ 0.90; disjoint RQ vectors."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if text.startswith("Naive Bayes"):
                vectors.append(_NB_NOISE_VECTOR.copy())
            elif text.startswith("Logistic Regression"):
                vectors.append(_LR_NOISE_VECTOR.copy())
            else:
                vectors.append([0.0, 0.0])
        return vectors


def _build_nb_lr_noise_live_graphs() -> tuple[dict, tuple[str, str]]:
    """Strong-noise live pair: Dataset_X vs Dataset_Y, no shared topology."""
    paper_a_id = "stem-soft-a"
    paper_b_id = "stem-soft-b"
    graphs = {
        paper_a_id: build_stem_graph_with_method_dataset_rq(
            paper_a_id,
            method_label="Naive Bayes",
            method_data={"description": "probabilistic generative classifier"},
            dataset_label="Dataset_X",
            question_label="Can Naive Bayes classify images in dataset X?",
        ),
        paper_b_id: build_stem_graph_with_method_dataset_rq(
            paper_b_id,
            method_label="Logistic Regression",
            method_data={"description": "discriminative linear classifier"},
            dataset_label="Dataset_Y",
            question_label="Does logistic regression improve accuracy on dataset Y?",
        ),
    }
    return graphs, (paper_a_id, paper_b_id)


@pytest.mark.asyncio
async def test_boundary_topology_veto_rejects_nb_lr_high_embedding_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """经典误配清洗：embedding≈0.90 通过初筛，但 Dataset_X/Y 拓扑交集为 0 → 一票否决。"""
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True, patrol_semantic_threshold=0.88)
    settings = get_settings()

    graphs, paper_ids = _build_nb_lr_noise_live_graphs()
    left_id, right_id = paper_ids
    left_graph = graphs[left_id]
    right_graph = graphs[right_id]
    left_methods = method_nodes(left_graph)
    right_methods = method_nodes(right_graph)
    embedding_client = _NbLrNoiseEmbeddingClient()

    nb_text = "Naive Bayes probabilistic generative classifier"
    lr_text = "Logistic Regression discriminative linear classifier"
    method_cosine = cosine_similarity(
        (await embedding_client.embed_texts([nb_text]))[0],
        (await embedding_client.embed_texts([lr_text]))[0],
    )
    assert method_cosine == pytest.approx(_LIVE_NB_LR_NOISE_COSINE, abs=1e-6)
    assert method_cosine >= settings.patrol_semantic_threshold

    assert _find_overlap_pairs(left_methods, right_methods, OverlapType.METHOD) == []

    left_neighbors = one_hop_neighbors(left_graph, left_methods[0].id)
    right_neighbors = one_hop_neighbors(right_graph, right_methods[0].id)
    left_datasets = {node.label for node in left_neighbors if node.type == NodeType.DATASET}
    right_datasets = {node.label for node in right_neighbors if node.type == NodeType.DATASET}
    assert left_datasets == {"Dataset_X"}
    assert right_datasets == {"Dataset_Y"}
    assert normalize_label("Dataset_X") not in {normalize_label(label) for label in right_datasets}

    assert not await has_topology_resonance(
        left_graph,
        right_graph,
        left_methods[0],
        right_methods[0],
        embedding_client=embedding_client,
        settings=settings,
    )

    semantic_anchor = await find_semantic_method_overlap(
        left_graph,
        right_graph,
        left_methods,
        right_methods,
        embedding_client,
        settings.patrol_semantic_threshold,
        settings.patrol_max_matrix_size,
        settings=settings,
    )
    assert semantic_anchor is None

    insight = await build_method_overlap_insight(
        graphs,
        list(paper_ids),
        embedding_client=embedding_client,
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
    assert insight.node_refs == []


_HSS_SHARED_SOFT_METHOD = "Textual Analysis"
_HSS_SHARED_SOFT_DATASET = "Interview Corpus"


def _build_hss_shared_soft_path_graphs() -> tuple[dict[str, UnifiedPaperGraph], tuple[str, str]]:
    """Two valid HSS papers sharing AnalyticalLens / ObjectOrData labels (soft-path bait)."""
    paper_a_id = "hss-soft-a"
    paper_b_id = "hss-soft-b"
    graphs = {
        paper_a_id: UnifiedPaperGraph(
            paper_id=paper_a_id,
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(
                    id="lens_a",
                    label=_HSS_SHARED_SOFT_METHOD,
                    type=NodeType.ANALYTICAL_LENS,
                    data={"description": "qualitative coding of interview transcripts"},
                ),
                GraphNode(
                    id="corpus_a",
                    label=_HSS_SHARED_SOFT_DATASET,
                    type=NodeType.OBJECT_OR_DATA,
                    data={"description": "semi-structured civic participation interviews"},
                ),
            ],
            edges=[
                GraphEdge(
                    id="e_examines_a",
                    source="lens_a",
                    target="corpus_a",
                    label="EXAMINES_THROUGH",
                    type="EXAMINES_THROUGH",
                ),
            ],
        ),
        paper_b_id: UnifiedPaperGraph(
            paper_id=paper_b_id,
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(
                    id="lens_b",
                    label=_HSS_SHARED_SOFT_METHOD,
                    type=NodeType.ANALYTICAL_LENS,
                    data={"description": "thematic discourse coding on the same corpus"},
                ),
                GraphNode(
                    id="corpus_b",
                    label=_HSS_SHARED_SOFT_DATASET,
                    type=NodeType.OBJECT_OR_DATA,
                    data={"description": "same interview corpus for deliberative norms"},
                ),
            ],
            edges=[
                GraphEdge(
                    id="e_examines_b",
                    source="lens_b",
                    target="corpus_b",
                    label="EXAMINES_THROUGH",
                    type="EXAMINES_THROUGH",
                ),
            ],
        ),
    }
    return graphs, (paper_a_id, paper_b_id)


def _stem_soft_path_bait_would_literal_match() -> bool:
    """Prove identical labels would literal-match on STEM Method nodes without paradigm gate."""
    stem_a = build_stem_graph_with_method_dataset_rq(
        "stem-bait-a",
        method_label=_HSS_SHARED_SOFT_METHOD,
        dataset_label=_HSS_SHARED_SOFT_DATASET,
        question_label="How does textual analysis frame civic participation?",
    )
    stem_b = build_stem_graph_with_method_dataset_rq(
        "stem-bait-b",
        method_id="n_method_b",
        method_label=_HSS_SHARED_SOFT_METHOD,
        dataset_id="n_dataset_b",
        dataset_label=_HSS_SHARED_SOFT_DATASET,
        question_id="n_question_b",
        question_label="Does textual analysis reveal deliberative norms?",
    )
    left_methods = method_nodes(stem_a)
    right_methods = method_nodes(stem_b)
    return bool(_find_overlap_pairs(left_methods, right_methods, OverlapType.METHOD))


@pytest.mark.asyncio
async def test_boundary_paradigm_gate_blocks_hss_before_topology_or_embedding(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """范式门禁红灯：两篇 HSS 塞入相同 Method 标签，入口即拦截，不进入拓扑/向量计算。"""
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True, patrol_semantic_threshold=0.88)

    graphs, paper_ids = _build_hss_shared_soft_path_graphs()
    left_id, right_id = paper_ids
    left_graph = graphs[left_id]
    right_graph = graphs[right_id]

    assert left_graph.paradigm == Paradigm.HSS
    assert right_graph.paradigm == Paradigm.HSS
    assert _stem_soft_path_bait_would_literal_match()

    spy_client = _SpyEmbeddingClient()

    def _forbidden_get_embedding_client() -> _SpyEmbeddingClient:
        raise AssertionError("get_embedding_client must not be called when paradigm gate blocks HSS")

    monkeypatch.setattr("backend.patrol.method_overlap.get_embedding_client", _forbidden_get_embedding_client)

    with (
        caplog.at_level(logging.INFO, logger=_METHOD_OVERLAP_LOGGER),
        patch(
            "backend.patrol.method_overlap.method_nodes",
            side_effect=AssertionError("method_nodes must not run after paradigm gate short-circuit"),
        ),
        patch(
            "backend.patrol.method_overlap.find_semantic_method_overlap",
            side_effect=AssertionError("find_semantic_method_overlap must not be called"),
        ),
        patch(
            "backend.patrol.method_overlap_topology.one_hop_neighbors",
            side_effect=AssertionError("one_hop_neighbors must not be called when paradigm gate blocks HSS"),
        ),
        patch(
            "backend.patrol.method_overlap_topology.has_topology_resonance",
            new_callable=AsyncMock,
            side_effect=AssertionError("has_topology_resonance must not be called"),
        ),
    ):
        insight = await build_method_overlap_insight(
            graphs,
            list(paper_ids),
            embedding_client=spy_client,
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
    assert insight.node_refs == []
    assert "HSS" in insight.summary

    audit_records = [record for record in caplog.records if record.getMessage() == "skipped_due_to_paradigm_mismatch"]
    assert len(audit_records) == 1
    assert audit_records[0].paper_ids == [left_id, right_id]  # type: ignore[attr-defined]

    with pytest.raises(AssertionError, match="must not be called when entry gate short-circuits"):
        await spy_client.embed_texts(["Textual Analysis"])
