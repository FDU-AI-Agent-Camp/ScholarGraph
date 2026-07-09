"""Unit tests for claim_evolution patrol mode (TDD red phase)."""

from unittest.mock import AsyncMock, patch

from backend.patrol.claim_evolution import build_claim_evolution_insight
from backend.schemas.patrol import (
    ClaimEvolutionPoint,
    PatrolInsightStatus,
    PatrolPoint,  # noqa: F401  used by type assertions
)
from tests.helpers.patrol_graphs import (
    build_hss_graph_with_question_claim,
    build_stem_graph_with_method_dataset,
    build_stem_graph_with_question_claim,
)


async def test_claim_evolution_ready_with_research_question() -> None:
    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
        "stem-002": build_stem_graph_with_question_claim(
            "stem-002",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率无显著变化",
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.insight_id == "ins-claim-evolution-001"
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert point.mode == "claim_evolution"
    assert "PCA" in point.research_question
    assert point.paper_a_claim
    assert point.paper_b_claim


async def test_claim_evolution_ready_with_hss_related_questions() -> None:
    """Two HSS papers on the same broad topic with diverging conclusions."""
    graphs = {
        "hss-001": build_hss_graph_with_question_claim(
            "hss-001",
            thesis_label="社交媒体使用是否促进青年政治参与？",
            claim_label="社交媒体显著提升政治参与意愿",
        ),
        "hss-002": build_hss_graph_with_question_claim(
            "hss-002",
            thesis_label="社交媒体对青年政治参与有何影响？",
            claim_label="社交媒体的影响被算法过滤气泡削弱",
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.structured_points
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert "社交媒体" in point.research_question
    assert "政治参与" in point.paper_a_claim or "政治参与" in point.paper_b_claim


async def test_claim_evolution_insufficient_with_hss_unrelated_questions() -> None:
    """Boundary: two HSS papers with completely unrelated topics return insufficient_data."""
    graphs = {
        "hss-001": build_hss_graph_with_question_claim(
            "hss-001",
            thesis_label="社交媒体使用是否促进青年政治参与？",
            claim_label="社交媒体显著提升政治参与意愿",
        ),
        "hss-002": build_hss_graph_with_question_claim(
            "hss-002",
            thesis_label="央行数字货币对货币政策传导机制的影响",
            claim_label="数字货币增强政策传导效率",
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


async def test_claim_evolution_ready_with_thesis_fallback() -> None:
    """Thesis nodes can act as research questions when similar and conclusions differ."""
    graphs = {
        "hss-001": build_hss_graph_with_question_claim(
            "hss-001",
            thesis_label="社交媒体使用是否促进青年政治参与？",
            claim_label="社交媒体显著提升政治参与意愿",
        ),
        "hss-002": build_hss_graph_with_question_claim(
            "hss-002",
            thesis_label="社交媒体对青年政治参与有何影响？",
            claim_label="社交媒体的影响被算法过滤气泡削弱",
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert "社交媒体" in point.research_question


async def test_claim_evolution_insufficient_when_same_conclusion() -> None:
    """Similar questions with identical claims do not represent claim evolution."""
    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
        "stem-002": build_stem_graph_with_question_claim(
            "stem-002",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


async def test_claim_evolution_ready_when_token_overlap_above_threshold() -> None:
    """Questions do not need to be identical; sufficient token overlap is enough."""
    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
        "stem-002": build_stem_graph_with_question_claim(
            "stem-002",
            question_label="分类准确率是否可以通过 PCA 提升？",
            claim_label="准确率无显著变化",
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert point.mode == "claim_evolution"


async def test_claim_evolution_insufficient_when_no_question_or_thesis() -> None:
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
    insight = await build_claim_evolution_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


async def test_claim_evolution_ready_when_no_claim() -> None:
    """If both papers have the same question and no claims, we cannot judge conclusion difference.

    Current MVP rule: only reject when both claims exist and are identical. Missing claims are
    treated as insufficient information to reject, so the insight is produced with placeholders.
    """
    from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    graphs = {
        "stem-001": UnifiedPaperGraph(
            paper_id="stem-001",
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n_q", label="Q1", type=NodeType.RESEARCH_QUESTION, data={})],
            edges=[],
        ),
        "stem-002": UnifiedPaperGraph(
            paper_id="stem-002",
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n_q", label="Q1", type=NodeType.RESEARCH_QUESTION, data={})],
            edges=[],
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["stem-001", "stem-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert point.evidence_summary


async def test_claim_evolution_rejects_wrong_paper_count() -> None:
    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label="Q1",
            claim_label="Claim A",
        ),
    }
    insight = await build_claim_evolution_insight(graphs, ["stem-001"])
    assert insight is None


async def test_claim_evolution_uses_vector_store_context() -> None:
    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = [
        AsyncMock(text="claim chunk for stem-001"),
        AsyncMock(text="another claim chunk for stem-001"),
    ]
    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
        "stem-002": build_stem_graph_with_question_claim(
            "stem-002",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率无显著变化",
        ),
    }
    with patch(
        "backend.patrol.claim_evolution.generate_patrol_summary",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_summary:
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            vector_store=vector_store,
        )
    assert insight is not None
    vector_store.query_chunks.assert_any_await(
        "research question thesis conclusion claim finding",
        paper_id="stem-001",
        top_k=3,
    )
    vector_store.query_chunks.assert_any_await(
        "research question thesis conclusion claim finding",
        paper_id="stem-002",
        top_k=3,
    )
    assert mock_summary.called
    context = mock_summary.call_args.args[1]
    assert "claim chunk for stem-001" in context
    assert "another claim chunk for stem-001" in context
