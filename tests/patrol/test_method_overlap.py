"""Unit tests for method_overlap patrol mode (TDD red phase)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import get_settings
from backend.patrol.method_overlap import build_method_overlap_insight
from backend.patrol.similarity import cosine_similarity
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
    build_stem_graph_dataset_only,
    build_stem_graph_with_method_dataset,
    build_stem_graph_with_method_dataset_rq,
    build_stem_graph_with_question_claim,
)
from tests.patrol.conftest import patch_patrol_settings


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
    assert insight.summary.startswith(llm_output.summary)
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
            "stem-001": build_stem_graph_with_method_dataset_rq(
                "stem-001",
                method_label="PCA",
                method_data={"description": "原始描述 A：主成分分析"},
                dataset_label="MNIST",
                question_label="Does PCA improve image classification accuracy?",
            ),
            "stem-002": build_stem_graph_with_method_dataset_rq(
                "stem-002",
                method_label="Principal Component Analysis",
                method_data={"description": "原始描述 B：PCA 变体"},
                dataset_label="CIFAR-10",
                question_label="Does PCA improve image classification accuracy?",
            ),
        }
        insight = await build_method_overlap_insight(
            graphs,
            ["stem-001", "stem-002"],
            embedding_client=_FakeEmbeddingClient(),
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.summary.startswith(llm_output.summary)
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
            "stem-001": build_stem_graph_with_method_dataset_rq(
                "stem-001",
                method_label="PCA",
                method_data={"description": "论文 A 用 PCA 提取 MNIST 主成分"},
                dataset_label="MNIST",
                question_label="Does PCA improve image classification accuracy?",
            ),
            "stem-002": build_stem_graph_with_method_dataset_rq(
                "stem-002",
                method_label="Principal Component Analysis",
                method_data={"description": "论文 B 用 PCA 压缩 CIFAR-10 特征"},
                dataset_label="CIFAR-10",
                question_label="Does PCA improve image classification accuracy?",
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
            "stem-001": build_stem_graph_with_method_dataset_rq(
                "stem-001",
                method_label="PCA",
                method_data={"description": "论文 A 用 PCA 做无监督降维"},
                dataset_label="MNIST",
                question_label="Does PCA improve image classification accuracy?",
            ),
            "stem-002": build_stem_graph_with_method_dataset_rq(
                "stem-002",
                method_label="Principal Component Analysis",
                method_data={"description": "论文 B 用 PCA 压缩特征"},
                dataset_label="CIFAR-10",
                question_label="Does PCA improve image classification accuracy?",
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


async def test_method_overlap_dual_overlap_flattens_to_method_and_dataset_points() -> None:
    """卡点：双重重合扁平化 — method 与 dataset 同时撞车时产出恰好 2 个独立 Point。"""
    llm_output = MethodOverlapOutput(
        summary="两篇论文均在 MNIST 上使用 PCA 进行特征压缩。",
        comparison_details=[
            MethodComparativeDetail(
                method_pair_name="PCA <-> PCA",
                paper_a_usage="论文 A 在 MNIST 上用 PCA 降维。",
                paper_b_usage="论文 B 在 MNIST 上用 PCA 提取主成分。",
                evidence_summary="方法层面均通过 PCA 压缩 MNIST 特征。",
            ),
            MethodComparativeDetail(
                method_pair_name="MNIST <-> MNIST",
                paper_a_usage="论文 A 在 MNIST 手写数字基准上评估分类准确率。",
                paper_b_usage="论文 B 复用 MNIST 基准比较不同降维维度。",
                evidence_summary="两篇论文共享 MNIST 实验数据语境。",
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
                method_id="m_pca_a",
                method_label="PCA",
                method_data={"usage": "PCA on MNIST"},
                dataset_id="ds_mnist_a",
                dataset_label="MNIST",
                dataset_data={"description": "Handwritten digit benchmark"},
            ),
            "stem-002": build_stem_graph_with_method_dataset(
                "stem-002",
                method_id="m_pca_b",
                method_label="PCA",
                method_data={"usage": "PCA feature compression"},
                dataset_id="ds_mnist_b",
                dataset_label="MNIST",
                dataset_data={"description": "Same digit benchmark"},
            ),
        }
        insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert len(insight.structured_points) == 2

    overlap_types = {point.overlap_type for point in insight.structured_points}
    assert overlap_types == {OverlapType.METHOD, OverlapType.DATASET}

    method_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.METHOD)
    dataset_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.DATASET)
    assert isinstance(method_point, MethodOverlapPoint)
    assert isinstance(dataset_point, MethodOverlapPoint)
    assert method_point.overlap_label == "PCA"
    assert dataset_point.overlap_label == "MNIST"
    assert method_point.evidence_summary == llm_output.comparison_details[0].evidence_summary
    assert dataset_point.evidence_summary == llm_output.comparison_details[1].evidence_summary
    assert {ref.node_id for ref in method_point.node_refs} == {"m_pca_a", "m_pca_b"}
    assert {ref.node_id for ref in dataset_point.node_refs} == {"ds_mnist_a", "ds_mnist_b"}
    assert {ref.node_id for ref in insight.node_refs} == {"m_pca_a", "m_pca_b", "ds_mnist_a", "ds_mnist_b"}


async def test_method_overlap_many_to_many_node_refs_collect_all_variant_nodes() -> None:
    """卡点：全量多对多 node_refs — 同标签多节点变体必须全部纳入 Point 锚定。"""
    graphs = {
        "stem-001": UnifiedPaperGraph(
            paper_id="stem-001",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(
                    id="m_pca_intro",
                    label="PCA",
                    type=NodeType.METHOD,
                    data={"usage": "PCA introduced in methodology section"},
                ),
                GraphNode(
                    id="m_pca_experiment",
                    label="PCA",
                    type=NodeType.METHOD,
                    data={"usage": "PCA applied in experiment pipeline"},
                ),
                GraphNode(id="ds_cifar_a", label="CIFAR-10", type=NodeType.DATASET, data={}),
            ],
            edges=[],
        ),
        "stem-002": UnifiedPaperGraph(
            paper_id="stem-002",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(
                    id="m_pca_main",
                    label="PCA",
                    type=NodeType.METHOD,
                    data={"usage": "PCA baseline in paper B"},
                ),
                GraphNode(
                    id="m_pca_ablation",
                    label="PCA",
                    type=NodeType.METHOD,
                    data={"usage": "PCA ablation variant in paper B"},
                ),
                GraphNode(id="ds_cifar_b", label="CIFAR-10", type=NodeType.DATASET, data={}),
            ],
            edges=[],
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert len(insight.structured_points) == 2

    method_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.METHOD)
    dataset_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.DATASET)
    assert method_point.overlap_label == "PCA"
    assert dataset_point.overlap_label == "CIFAR-10"

    expected_method_ids = {"m_pca_intro", "m_pca_experiment", "m_pca_main", "m_pca_ablation"}
    expected_dataset_ids = {"ds_cifar_a", "ds_cifar_b"}
    assert {ref.node_id for ref in method_point.node_refs} == expected_method_ids
    assert {ref.paper_id for ref in method_point.node_refs if ref.node_id.startswith("m_pca_")} == {
        "stem-001",
        "stem-002",
    }
    assert {ref.node_id for ref in dataset_point.node_refs} == expected_dataset_ids
    assert {ref.node_id for ref in insight.node_refs} == expected_method_ids | expected_dataset_ids
    assert len(method_point.node_refs) == len(expected_method_ids)
    assert len(dataset_point.node_refs) == len(expected_dataset_ids)


async def test_method_overlap_dataset_only_anchors_to_dataset_nodes() -> None:
    """Dataset-only overlap must produce DATASET point with dataset node refs and usage."""
    graphs = {
        "stem-001": build_stem_graph_dataset_only(
            "stem-001",
            method_label="PCA",
            dataset_id="ds_mnist_001",
            dataset_label="MNIST",
            dataset_data={"description": "Handwritten digit benchmark with 70,000 grayscale images."},
        ),
        "stem-002": build_stem_graph_dataset_only(
            "stem-002",
            method_label="Random Forest",
            dataset_id="ds_mnist_002",
            dataset_label="MNIST",
            dataset_data={"description": "Same handwritten digit dataset used to evaluate tree ensembles."},
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, MethodOverlapPoint)
    assert point.overlap_type == OverlapType.DATASET
    assert point.overlap_label == "MNIST"
    # node_refs must point to the dataset nodes, not the method nodes.
    ref_ids = {ref.node_id for ref in point.node_refs}
    assert ref_ids == {"ds_mnist_001", "ds_mnist_002"}
    assert {ref.node_id for ref in insight.node_refs} == ref_ids
    # Usage must come from the dataset description, not from the method label.
    assert "Handwritten" in point.paper_a_usage
    assert "tree ensembles" in point.paper_b_usage
    assert "PCA" not in point.paper_a_usage
    assert "Random Forest" not in point.paper_b_usage


async def test_method_overlap_hss_gate_ignores_shared_method_labels() -> None:
    """Two HSS papers with identical method labels must still be rejected by paradigm gate."""
    graphs = {
        "hss-001": UnifiedPaperGraph(
            paper_id="hss-001",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="m_text_analysis_1", label="Textual Analysis", type=NodeType.ANALYTICAL_LENS, data={}),
            ],
            edges=[],
        ),
        "hss-002": UnifiedPaperGraph(
            paper_id="hss-002",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="m_text_analysis_2", label="Textual Analysis", type=NodeType.ANALYTICAL_LENS, data={}),
            ],
            edges=[],
        ),
    }
    insight = await build_method_overlap_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
    assert insight.node_refs == []


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
    assert insight.summary.startswith(llm_output.summary)
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
    # Query is now graph-topology-guided: the aligned anchor label PCA is injected.
    vector_store.query_chunks.assert_any_await("PCA 具体应用场景 数据集配置 实验数值特征", paper_id="stem-001", top_k=3)
    vector_store.query_chunks.assert_any_await("PCA 具体应用场景 数据集配置 实验数值特征", paper_id="stem-002", top_k=3)
    # When vector_store is supplied and exists() returns True, no degradation flag is set.
    assert "patrol_rag_context_degraded" not in insight.meta
    assert mock_summary.called
    context = mock_summary.call_args.args[0]
    assert "chunk text for stem-001" in context
    assert "another chunk for stem-001" in context


async def test_method_overlap_records_rag_degradation_when_index_missing() -> None:
    """If VectorStore index is missing, READY insight carries patrol_rag_context_degraded meta."""
    vector_store = AsyncMock()
    vector_store.exists.return_value = False
    vector_store.query_chunks.return_value = []
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
    ):
        insight = await build_method_overlap_insight(
            graphs,
            ["stem-001", "stem-002"],
            vector_store=vector_store,
        )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.meta.get("patrol_rag_context_degraded", {}).get("reason") == "index_not_ready"
    assert set(insight.meta["patrol_rag_context_degraded"]["paper_ids"]) == {"stem-001", "stem-002"}


async def test_method_overlap_chinese_description_recall() -> None:
    """Dynamic Chinese query must recall a Chinese method-description chunk."""
    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = [
        AsyncMock(text="使用卷积神经网络对图像进行特征提取，并在 ImageNet 上验证了效果。"),
    ]
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="卷积神经网络",
            method_data={"description": "使用卷积神经网络对图像进行特征提取"},
            dataset_label="ImageNet",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="卷积神经网络",
            method_data={"description": "使用卷积神经网络对图像进行特征提取"},
            dataset_label="CIFAR-10",
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
    assert insight.status == PatrolInsightStatus.READY
    # The dynamic query should be anchored by the overlapping Chinese label.
    queries = {}
    for call in vector_store.query_chunks.call_args_list:
        query = call.args[0] if call.args else call.kwargs.get("query")
        paper_id = call.kwargs.get("paper_id") or call.args[1]
        queries[paper_id] = query
    for paper_id in ("stem-001", "stem-002"):
        assert "卷积神经网络" in queries[paper_id]
        assert "具体应用场景" in queries[paper_id]
    context = mock_summary.call_args.args[0]
    assert "使用卷积神经网络对图像进行特征提取" in context


class _FakeEmbeddingClient:
    """Deterministic embedding client for semantic overlap tests.

    Vectors are keyed by the embedded text so callers can control which
    method labels/descriptions are considered semantically similar.
    """

    def __init__(self, threshold: float = 0.88) -> None:
        self.is_mock = False
        self._threshold = threshold

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: dict[str, list[float]] = {}
        for text in texts:
            if "PCA" in text or "Principal Component Analysis" in text:
                vectors[text] = [1.0, 0.0] if text.startswith("PCA") else [0.99, 0.01]
            elif "Naive Bayes" in text:
                vectors[text] = [0.9, 0.43]
            elif "Logistic Regression" in text:
                vectors[text] = [0.88, 0.47]
            else:
                vectors[text] = [0.0, 0.0]
        return [vectors.get(text, [0.0, 0.0]).copy() for text in texts]

    @property
    def threshold(self) -> float:
        return self._threshold


# Live defect regression vectors (bge-m3 stem-soft-a/b corpus).
_LIVE_NB_LR_COSINE = 0.82
_NB_LIVE_DEFECT_VECTOR = [1.0, 0.0]
_LR_LIVE_DEFECT_VECTOR = [_LIVE_NB_LR_COSINE, math.sqrt(1.0 - _LIVE_NB_LR_COSINE**2)]


class _NbLrLiveDefectEmbeddingClient:
    """Reproduce live false-positive: NB ↔ LR cosine ≈ 0.82 with disjoint datasets."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "Naive Bayes" in text:
                vectors.append(_NB_LIVE_DEFECT_VECTOR.copy())
            elif "Logistic Regression" in text:
                vectors.append(_LR_LIVE_DEFECT_VECTOR.copy())
            else:
                vectors.append([0.0, 0.0])
        return vectors


class _PcaSynonymLiveDefectEmbeddingClient:
    """Reproduce live true-positive: PCA ↔ Principal Component Analysis high cosine."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: dict[str, list[float]] = {}
        for text in texts:
            if text.startswith("PCA") or text.startswith("PCA "):
                vectors[text] = [1.0, 0.0]
            elif "Principal Component Analysis" in text:
                vectors[text] = [0.99, 0.01]
            else:
                vectors[text] = [0.0, 0.0]
        return [vectors.get(text, [0.0, 0.0]).copy() for text in texts]


@pytest.mark.asyncio
async def test_live_defect_naive_bayes_vs_logistic_regression_blocked_by_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """经典误配防御：NB↔LR embedding≈0.82 但无公共 Dataset/RQ 拓扑 → INSUFFICIENT_DATA."""
    patch_patrol_settings(monkeypatch, patrol_semantic_threshold=0.75)
    settings = get_settings()

    nb_text = "Naive Bayes probabilistic generative classifier"
    lr_text = "Logistic Regression discriminative linear classifier"
    assert cosine_similarity(_NB_LIVE_DEFECT_VECTOR, _LR_LIVE_DEFECT_VECTOR) == pytest.approx(
        _LIVE_NB_LR_COSINE,
        abs=1e-6,
    )

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
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-soft-a", "stem-soft-b"],
        embedding_client=_NbLrLiveDefectEmbeddingClient(),
    )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
    assert (
        cosine_similarity(
            (await _NbLrLiveDefectEmbeddingClient().embed_texts([nb_text]))[0],
            (await _NbLrLiveDefectEmbeddingClient().embed_texts([lr_text]))[0],
        )
        >= settings.patrol_semantic_threshold
    )


@pytest.mark.asyncio
async def test_live_defect_pca_vs_principal_component_analysis_passes_with_mnist_resonance() -> None:
    """同义词对提取：PCA↔全名 + 共享 MNIST 数据集拓扑共振 → READY 且高分 semantic。"""
    shared_dataset = "MNIST"
    graphs = {
        "stem-soft-a": build_stem_graph_with_method_dataset(
            "stem-soft-a",
            method_label="PCA",
            method_data={"description": "linear dimensionality reduction for image features"},
            dataset_label=shared_dataset,
        ),
        "stem-soft-b": build_stem_graph_with_method_dataset(
            "stem-soft-b",
            method_label="Principal Component Analysis",
            method_data={"description": "principal components for image feature compression"},
            dataset_label=shared_dataset,
        ),
    }
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-soft-a", "stem-soft-b"],
        embedding_client=_PcaSynonymLiveDefectEmbeddingClient(),
    )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert len(insight.structured_points) == 2
    method_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.METHOD)
    assert isinstance(method_point, MethodOverlapPoint)
    assert method_point.mode == "method_overlap"
    assert method_point.overlap_type == OverlapType.METHOD
    assert method_point.match_type == "semantic"
    assert method_point.overlap_score is not None
    assert method_point.overlap_score >= get_settings().patrol_semantic_threshold
    assert method_point.method == "PCA"
    assert method_point.overlap_label == "PCA"
    dataset_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.DATASET)
    assert dataset_point.overlap_label == shared_dataset
    assert {ref.label for ref in method_point.node_refs} == {"PCA", "Principal Component Analysis"}
    assert {ref.label for ref in dataset_point.node_refs} == {shared_dataset}


async def test_method_overlap_ready_with_semantic_method_match() -> None:
    """Soft path: labels differ but descriptions and topology identify the same method."""
    shared_dataset = "MNIST"
    shared_question = "Does dimensionality reduction improve image classification accuracy?"
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset_rq(
            "stem-001",
            method_label="PCA",
            method_data={"description": "线性降维"},
            dataset_label=shared_dataset,
            question_label=shared_question,
        ),
        "stem-002": build_stem_graph_with_method_dataset_rq(
            "stem-002",
            method_label="Principal Component Analysis",
            method_data={"description": "线性降维"},
            dataset_label=shared_dataset,
            question_label=shared_question,
        ),
    }
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=_FakeEmbeddingClient(),
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    method_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.METHOD)
    assert isinstance(method_point, MethodOverlapPoint)
    assert method_point.overlap_type == OverlapType.METHOD
    assert method_point.match_type == "semantic"
    assert method_point.overlap_score is not None
    assert 0.0 < method_point.overlap_score < 1.0
    assert method_point.overlap_score >= 0.88
    assert method_point.method == "PCA"
    assert method_point.overlap_label == "PCA"
    dataset_point = next(p for p in insight.structured_points if p.overlap_type == OverlapType.DATASET)
    assert dataset_point.overlap_label == shared_dataset


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


async def test_method_overlap_rejects_semantic_noise_without_topology_resonance() -> None:
    """High embedding similarity alone is insufficient when datasets and RQs differ."""
    graphs = {
        "stem-001": build_stem_graph_with_method_dataset_rq(
            "stem-001",
            method_label="Naive Bayes",
            method_data={"description": "Generative classifier"},
            dataset_label="MNIST",
            question_label="Can generative models classify handwritten digits?",
        ),
        "stem-002": build_stem_graph_with_method_dataset_rq(
            "stem-002",
            method_label="Logistic Regression",
            method_data={"description": "Discriminative classifier"},
            dataset_label="CIFAR-10",
            question_label="Does logistic regression improve object recognition?",
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


async def test_method_overlap_semantic_path_disabled_skips_embedding(monkeypatch) -> None:
    """ENABLE_PATROL_SEMANTIC_PATH=false forces literal-only matching."""
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=False)

    graphs = {
        "stem-001": build_stem_graph_with_method_dataset_rq(
            "stem-001",
            method_label="PCA",
            method_data={"description": "线性降维"},
            dataset_label="Dataset A",
            question_label="Question A",
        ),
        "stem-002": build_stem_graph_with_method_dataset_rq(
            "stem-002",
            method_label="Principal Component Analysis",
            method_data={"description": "线性降维"},
            dataset_label="Dataset B",
            question_label="Question B",
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
    # ``0`` is intentionally below the Settings schema floor (ge=1); setattr the
    # cached singleton for this edge case — autouse teardown clears it afterward.
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


class _ExplodingEmbeddingClient:
    """Simulates live embedding 404 / timeout without is_mock."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("model `bge-m3` does not exist")


@pytest.mark.asyncio
async def test_find_semantic_method_overlap_degrades_on_embedding_failure() -> None:
    from backend.patrol.method_overlap_semantic import find_semantic_method_overlap

    graphs = {
        "stem-001": build_stem_graph_with_method_dataset_rq(
            "stem-001",
            method_label="PCA",
            dataset_label="MNIST",
            question_label="Does PCA help?",
        ),
        "stem-002": build_stem_graph_with_method_dataset_rq(
            "stem-002",
            method_label="Principal Component Analysis",
            dataset_label="MNIST",
            question_label="Can PCA help?",
        ),
    }
    left_graph = graphs["stem-001"]
    right_graph = graphs["stem-002"]
    left_methods = [node for node in left_graph.nodes if node.type == NodeType.METHOD]
    right_methods = [node for node in right_graph.nodes if node.type == NodeType.METHOD]
    settings = get_settings()

    anchor = await find_semantic_method_overlap(
        left_graph,
        right_graph,
        left_methods,
        right_methods,
        _ExplodingEmbeddingClient(),
        settings.patrol_semantic_threshold,
        settings.patrol_max_matrix_size,
        settings=settings,
    )

    assert anchor is None


@pytest.mark.asyncio
async def test_method_overlap_semantic_embedding_failure_falls_back_to_dataset_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semantic path failure must not 500; literal dataset overlap still produces READY."""
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True)

    graphs = {
        "stem-001": build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="MNIST",
        ),
        "stem-002": build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="Principal Component Analysis",
            dataset_label="MNIST",
        ),
    }
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=_ExplodingEmbeddingClient(),
    )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert len(insight.structured_points) == 1
    assert insight.structured_points[0].overlap_type == OverlapType.DATASET
