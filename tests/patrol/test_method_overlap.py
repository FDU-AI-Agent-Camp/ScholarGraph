"""Unit tests for method_overlap patrol mode (TDD red phase)."""

from unittest.mock import AsyncMock, patch

from backend.patrol.method_overlap import build_method_overlap_insight
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.schemas.patrol import (
    MethodOverlapPoint,
    OverlapType,
    PatrolInsightStatus,
    PatrolPoint,  # noqa: F401  used by type assertions
)
from backend.schemas.patrol_llm import MethodComparativeDetail, MethodOverlapOutput
from tests.helpers.patrol_graphs import (
    build_hss_graph_with_question_claim,
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
    assert point.overlap_label == "PCA"
    assert point.overlap_type == OverlapType.METHOD
    assert point.match_type == "literal"
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
    # Method overlap keeps dataset_a/dataset_b as optional side information.
    assert point.dataset_a is None
    assert point.dataset_b is None


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


async def test_method_overlap_perfect_llm_alignment_overrides_node_usage() -> None:
    """Perfect LLM output should override raw node usage and evidence_summary."""
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
                method_data={"usage": "原始节点 usage A", "description": "原始节点 description A"},
                dataset_label="MNIST",
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_label="PCA",
                method_data={"usage": "原始节点 usage B", "description": "原始节点 description B"},
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
    assert "原始节点" not in point.paper_a_usage
    assert "原始节点" not in point.paper_b_usage


async def test_method_overlap_hallucinated_pair_name_falls_back_to_node_description() -> None:
    """LLM returns a mismatched pair name; system should fallback to node description without crashing."""
    llm_output = MethodOverlapOutput(
        summary="两篇论文的核心方法都涉及支持向量机分类器的设计与验证。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name="SVM <-> Support Vector Machine",
                paper_a_usage="论文 A 使用 SVM 做分类",
                paper_b_usage="论文 B 也使用 SVM 做分类",
                evidence_summary="SVM 是核心分类器",
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
                method_data={"description": "论文 A 用 PCA 做无监督降维"},
                dataset_label="MNIST",
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_label="PCA",
                method_data={"description": "论文 B 用 PCA 压缩特征"},
                dataset_label="CIFAR-10",
            ),
        }
        insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.structured_points
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.method == "PCA"
    assert point.paper_a_usage == "论文 A 用 PCA 做无监督降维"
    assert point.paper_b_usage == "论文 B 用 PCA 压缩特征"
    assert point.evidence_summary is None


async def test_alignment_merger_perfect_match_with_semantic_pair() -> None:
    """路径 A：算法发现 PCA <-> Principal Component Analysis，LLM 完美匹配，语义被完整吸收。"""
    llm_output = MethodOverlapOutput(
        summary="两篇论文均采用主成分分析对高维图像特征进行线性降维与去噪处理。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name="PCA <-> Principal Component Analysis",
                paper_a_usage="论文 A 使用 PCA 对 MNIST 图像进行降维，保留 95% 累计方差。",
                paper_b_usage="论文 B 将 Principal Component Analysis 应用于 CIFAR-10 颜色通道压缩。",
                evidence_summary="两者均利用主成分分析降低输入维度，但论文 B 在更复杂的彩色图像上验证效果。",
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
                method_data={"description": "原始描述 A：主成分分析"},
                dataset_label="MNIST",
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_label="Principal Component Analysis",
                method_data={"description": "原始描述 B：PCA 变体"},
                dataset_label="CIFAR-10",
            ),
        }
        insight = await build_method_overlap_insight(
            graphs,
            ["stem-001", "stem-002"],
            embedding_client=_FakeEmbeddingClient(),
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.summary == llm_output.summary
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.method == "PCA"
    assert point.paper_a_usage == llm_output.comparison_details[0].paper_a_usage
    assert point.paper_b_usage == llm_output.comparison_details[0].paper_b_usage
    assert point.evidence_summary == llm_output.comparison_details[0].evidence_summary
    assert "原始描述" not in (point.paper_a_usage + (point.paper_b_usage or ""))


async def test_alignment_merger_hallucinated_pair_name_falls_back_to_description() -> None:
    """路径 B：算法发现 PCA <-> Principal Component Analysis，LLM 配对名错误，系统不崩溃并降级。"""
    llm_output = MethodOverlapOutput(
        summary="两篇论文都讨论了支持向量机在文本分类任务中的应用差异。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name="SVM <-> Support Vector Machine",
                paper_a_usage="论文 A 使用 SVM 进行文本分类",
                paper_b_usage="论文 B 使用 SVM 进行情感分析",
                evidence_summary="SVM 核函数选择不同导致性能差异",
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
                method_data={"description": "论文 A 用 PCA 提取 MNIST 主成分"},
                dataset_label="MNIST",
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_label="Principal Component Analysis",
                method_data={"description": "论文 B 用 PCA 压缩 CIFAR-10 特征"},
                dataset_label="CIFAR-10",
            ),
        }
        insight = await build_method_overlap_insight(
            graphs,
            ["stem-001", "stem-002"],
            embedding_client=_FakeEmbeddingClient(),
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.structured_points
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.method == "PCA"
    assert point.paper_a_usage == "论文 A 用 PCA 提取 MNIST 主成分"
    assert point.paper_b_usage == "论文 B 用 PCA 压缩 CIFAR-10 特征"
    assert point.evidence_summary is None


async def test_alignment_merger_malformed_llm_output_returns_ready_with_fallback() -> None:
    """路径 B 扩展：LLM 返回 None 或残缺输出时仍应 READY 并 fallback。"""
    with patch(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        graphs = {
            "stem-001": build_stem_graph_with_method_dataset(
                "stem-001",
                method_label="PCA",
                method_data={"description": "论文 A 用 PCA 做无监督降维"},
                dataset_label="MNIST",
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_label="Principal Component Analysis",
                method_data={"description": "论文 B 用 PCA 压缩特征"},
                dataset_label="CIFAR-10",
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
    assert point.paper_a_usage == "论文 A 用 PCA 做无监督降维"
    assert point.paper_b_usage == "论文 B 用 PCA 压缩特征"


async def test_method_overlap_skips_hss_paradigm() -> None:
    """HSS papers should short-circuit and return INSUFFICIENT_DATA."""
    graphs = {
        "hss-001": build_hss_graph_with_question_claim(
            "hss-001",
            thesis_label="数字民主",
            claim_label="社交媒体提升政治参与",
        ),
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["hss-001", "stem-001"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
    assert "HSS" in insight.summary


async def test_method_overlap_skips_both_hss_papers() -> None:
    """Two HSS papers should also short-circuit without crashing."""
    graphs = {
        "hss-001": build_hss_graph_with_question_claim(
            "hss-001",
            thesis_label="数字民主",
            claim_label="社交媒体提升政治参与",
        ),
        "hss-002": build_hss_graph_with_question_claim(
            "hss-002",
            thesis_label="公共领域",
            claim_label="微博使用提升投票率",
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


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

    def __init__(self, threshold: float = 0.75) -> None:
        self.is_mock = False
        self._threshold = threshold

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: dict[str, list[float]] = {}
        for text in texts:
            if "PCA" in text or "Principal Component Analysis" in text:
                # Deterministic but different vectors for PCA-related texts.
                vectors[text] = [1.0, 0.0] if text.startswith("PCA") else [0.99, 0.01]
            else:
                vectors[text] = [0.0, 0.0]
        return [vectors.get(text, [0.0, 0.0]).copy() for text in texts]

    @property
    def threshold(self) -> float:
        return self._threshold


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
    assert point.overlap_type == OverlapType.METHOD
    assert point.match_type == "semantic"
    assert point.overlap_score is not None
    assert 0.0 < point.overlap_score < 1.0
    assert point.overlap_score >= 0.75
    assert point.method == "PCA"
    assert point.overlap_label == "PCA"


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
