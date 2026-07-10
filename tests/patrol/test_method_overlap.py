"""Unit tests for method_overlap patrol mode (TDD red phase)."""

from unittest.mock import AsyncMock, patch

from backend.patrol.method_overlap import build_method_overlap_insight
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol import (
    MethodOverlapPoint,
    PatrolInsightStatus,
    PatrolPoint,  # noqa: F401  used by type assertions
)
from backend.schemas.patrol_llm import MethodComparativeDetail, MethodOverlapOutput
from tests.helpers.patrol_graphs import (
    build_stem_graph_with_method_dataset,
    build_stem_graph_with_question_claim,
)


async def test_method_overlap_ready_two_methods() -> None:
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="Dataset B",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.insight_id == "ins-method-overlap-001"
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.mode == "method_overlap"
    assert point.method == "PCA"
    assert point.overlap_type == "literal"
    assert point.overlap_score == 1.0
    assert point.paper_a_usage
    assert point.paper_b_usage


async def test_method_overlap_insufficient_when_no_method() -> None:
    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label="Q1",
            claim_label="Claim A",
        ),
        "stem-002": build_stem_graph_with_question_claim(
            "stem-002",
            question_label="Q2",
            claim_label="Claim B",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


async def test_method_overlap_includes_dataset_when_present() -> None:
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="MNIST",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="CIFAR-10",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.dataset_a == "MNIST"
    assert point.dataset_b == "CIFAR-10"


async def test_method_overlap_fallback_summary_when_llm_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        AsyncMock(return_value=None),
    )
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="Dataset B",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert "PCA" in insight.summary


async def test_method_overlap_insufficient_when_no_overlap() -> None:
    """Boundary: two papers with different methods and datasets should not trigger overlap."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="MNIST",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="Random Forest",
            dataset_label="CIFAR-10",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


async def test_method_overlap_ready_when_dataset_overlaps() -> None:
    """Two papers using different methods but the same dataset still trigger overlap."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="MNIST",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="Random Forest",
            dataset_label="MNIST",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.method == "MNIST"
    assert point.dataset_a == "MNIST"
    assert point.dataset_b == "MNIST"


async def test_method_overlap_case_insensitive_match() -> None:
    """Normalized labels should match regardless of case; returned casing follows the left paper."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="pca",
            dataset_label="Dataset B",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.method == "PCA"


async def test_method_overlap_uses_node_usage_when_available() -> None:
    """paper_a_usage / paper_b_usage should come from node.data['usage'] when present."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            method_data={"usage": "用于降维"},
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            method_data={"usage": "用于特征选择"},
            dataset_label="Dataset B",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.paper_a_usage == "用于降维"
    assert point.paper_b_usage == "用于特征选择"


async def test_method_overlap_uses_fallback_template_without_usage() -> None:
    """MVP fallback: usage is '用于 {method_label}' when node.data has no usage."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="Dataset B",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.paper_a_usage == "用于 PCA"
    assert point.paper_b_usage == "用于 PCA"


async def test_method_overlap_fallback_when_llm_misses_pair() -> None:
    """Alignment merger should fall back to node usage when LLM omits a pair."""
    llm_output = MethodOverlapOutput(
        summary="两篇论文在方法层面存在重叠，需要进一步对比实验设计差异。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name="SVM <-> SVM",
                paper_a_usage="论文 A 的 SVM 使用说明很长",
                paper_b_usage="论文 B 的 SVM 使用说明也很长",
                evidence_summary="SVM 相关证据摘要",
            ),
        ],
    )
    with patch(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        new_callable=AsyncMock,
        return_value=llm_output,
    ):
        graphs = {
            "stem-001": build_stem_graph_with_method_dataset(
                "stem-001",
                method_label="PCA",
                method_data={"usage": "论文 A 用 PCA 降维"},
                dataset_label="MNIST",
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_label="PCA",
                method_data={"usage": "论文 B 用 PCA 提取主成分"},
                dataset_label="CIFAR-10",
            ),
        }
        insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])

    assert insight is not None
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.method == "PCA"
    assert point.paper_a_usage == "论文 A 用 PCA 降维"
    assert point.paper_b_usage == "论文 B 用 PCA 提取主成分"
    assert point.evidence_summary is None


async def test_method_overlap_aligns_multiple_literal_pairs() -> None:
    """Two shared method labels should produce two anchored structured points."""
    llm_output = MethodOverlapOutput(
        summary="两篇论文均使用了 PCA 与 SVM 两种方法，并在不同数据集上进行了验证。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name="PCA <-> PCA",
                paper_a_usage="PCA usage in paper A",
                paper_b_usage="PCA usage in paper B",
                evidence_summary="PCA evidence summary",
            ),
            MethodComparativeDetail(
                method_pair_name="SVM <-> SVM",
                paper_a_usage="SVM usage in paper A",
                paper_b_usage="SVM usage in paper B",
                evidence_summary="SVM evidence summary",
            ),
        ],
    )
    with patch(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        new_callable=AsyncMock,
        return_value=llm_output,
    ):
        graphs = {
            "stem-001": UnifiedPaperGraph(
                paper_id="stem-001",
                paradigm=Paradigm.STEM,
                nodes=[
                    GraphNode(id="m1", label="PCA", type=NodeType.METHOD, data={}),
                    GraphNode(id="m2", label="SVM", type=NodeType.METHOD, data={}),
                ],
                edges=[],
            ),
            "stem-002": UnifiedPaperGraph(
                paper_id="stem-002",
                paradigm=Paradigm.STEM,
                nodes=[
                    GraphNode(id="m3", label="PCA", type=NodeType.METHOD, data={}),
                    GraphNode(id="m4", label="SVM", type=NodeType.METHOD, data={}),
                ],
                edges=[],
            ),
        }
        insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])

    assert insight is not None
    assert len(insight.structured_points) == 2
    methods = {point.method for point in insight.structured_points}
    assert methods == {"PCA", "SVM"}
    for point in insight.structured_points:
        assert isinstance(point, MethodOverlapPoint)
        assert "usage in paper A" in point.paper_a_usage
        assert "usage in paper B" in point.paper_b_usage


async def test_method_overlap_rejects_wrong_paper_count() -> None:
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001"])
    assert insight is None


async def test_method_overlap_uses_structured_llm_output_when_available() -> None:
    """When LLM returns MethodOverlapOutput, structured_points should use LLM fields."""
    llm_output = MethodOverlapOutput(
        summary="两篇论文均在图像分类任务中使用了 PCA 进行降维。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name="PCA <-> PCA",
                paper_a_usage="论文 A 将 PCA 用于 MNIST 手写数字特征压缩，保留 95% 方差。",
                paper_b_usage="论文 B 将 PCA 用于 CIFAR-10 图像降维，保留 90% 方差。",
                evidence_summary="两者都通过 PCA 降低输入维度，但论文 B 在更复杂的彩色图像上验证了效果。",
            ),
        ],
    )
    with patch(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        new_callable=AsyncMock,
        return_value=llm_output,
    ):
        graphs = {
            "stem-001": build_stem_graph_with_method_dataset(
                "stem-001",
                method_label="PCA",
                method_data={"usage": "用于降维"},
                dataset_label="MNIST",
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_label="PCA",
                method_data={"usage": "用于特征选择"},
                dataset_label="CIFAR-10",
            ),
        }
        insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.summary == llm_output.summary
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.paper_a_usage == llm_output.comparison_details[0].paper_a_usage
    assert point.paper_b_usage == llm_output.comparison_details[0].paper_b_usage
    assert point.evidence_summary == llm_output.comparison_details[0].evidence_summary


async def test_method_overlap_uses_vector_store_context() -> None:
    from unittest.mock import AsyncMock, patch

    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = [
        AsyncMock(text="chunk text for stem-001"),
        AsyncMock(text="another chunk for stem-001"),
    ]
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="Dataset B",
        ),
    }
    with patch(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_summary:
        insight = await build_method_overlap_insight(
            graphs,
            ["stem-001", "stem-002"],
            vector_store=vector_store,
        )
    assert insight is not None
    vector_store.query_chunks.assert_any_await("method dataset experimental setup", paper_id="stem-001", top_k=3)
    vector_store.query_chunks.assert_any_await("method dataset experimental setup", paper_id="stem-002", top_k=3)
    assert mock_summary.called
    context = mock_summary.call_args.args[0]
    assert "chunk text for stem-001" in context
    assert "another chunk for stem-001" in context


class _FakeEmbeddingClient:
    """Deterministic embedding client for semantic overlap tests.

    Vectors are keyed by the embedded text so callers can control which
    method labels/descriptions are considered semantically similar.
    """

    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {
            "PCA 线性降维": [1.0, 0.0],
            "Principal Component Analysis 线性降维": [0.95, 0.31],
            "Random Forest 集成学习": [0.0, 1.0],
            "SVM 支持向量机": [0.0, 0.0],
        }
        self.is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors.get(text, [0.0, 0.0]).copy() for text in texts]


async def test_method_overlap_ready_with_semantic_method_match() -> None:
    """Soft path: labels differ but descriptions identify the same method."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            method_data={"description": "线性降维"},
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="Principal Component Analysis",
            method_data={"description": "线性降维"},
            dataset_label="Dataset B",
        ),
    }
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=_FakeEmbeddingClient(),
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.overlap_type == "semantic"
    assert point.overlap_score is not None
    assert 0.0 < point.overlap_score < 1.0
    assert point.overlap_score >= 0.75
    assert point.method == "PCA"


async def test_method_overlap_insufficient_when_semantic_match_below_threshold() -> None:
    """Soft path should not trigger when embeddings are orthogonal."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            method_data={"description": "线性降维"},
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="Random Forest",
            method_data={"description": "集成学习"},
            dataset_label="Dataset B",
        ),
    }
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=_FakeEmbeddingClient(),
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


async def test_method_overlap_degrades_when_matrix_too_large(monkeypatch) -> None:
    """When M*N exceeds PATROL_MAX_MATRIX_SIZE, fall back to literal matching only."""
    from backend.config import get_settings

    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            method_data={"description": "线性降维"},
            dataset_label="Dataset A",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="Principal Component Analysis",
            method_data={"description": "线性降维"},
            dataset_label="Dataset B",
        ),
    }
    settings = get_settings()
    monkeypatch.setattr(settings, "patrol_max_matrix_size", 0)
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=_FakeEmbeddingClient(),
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
