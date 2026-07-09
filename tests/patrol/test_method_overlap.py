"""Unit tests for method_overlap patrol mode (TDD red phase)."""

from unittest.mock import AsyncMock

from backend.patrol.method_overlap import build_method_overlap_insight
from backend.schemas.patrol import (
    MethodOverlapPoint,
    PatrolInsightStatus,
    PatrolPoint,  # noqa: F401  used by type assertions
)
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
        "backend.patrol.method_overlap.generate_patrol_summary",
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


async def test_method_overlap_uses_vector_store_context() -> None:
    vector_store = AsyncMock()
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
    insight = await build_method_overlap_insight(
        graphs,
        ["stem-001", "stem-002"],
        vector_store=vector_store,
    )
    assert insight is not None
    vector_store.query_chunks.assert_any_await("method dataset experimental setup", paper_id="stem-001", top_k=3)
    vector_store.query_chunks.assert_any_await("method dataset experimental setup", paper_id="stem-002", top_k=3)
