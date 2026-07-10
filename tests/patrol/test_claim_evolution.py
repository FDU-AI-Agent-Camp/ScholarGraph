"""Unit tests for claim_evolution patrol mode."""

from unittest.mock import AsyncMock, patch

from backend.patrol.claim_evolution import build_claim_evolution_insight
from backend.schemas.patrol import (
    ClaimEvolutionPoint,
    EvolutionType,
    PatrolInsightStatus,
    PatrolPoint,  # noqa: F401  used by type assertions
)
from tests.helpers.patrol_graphs import (
    build_hss_graph_with_question_claim,
    build_stem_graph_with_method_dataset,
    build_stem_graph_with_question_claim,
)


class _FakeEmbeddingClient:
    """Deterministic embedding client for claim-evolution tests.

    Vectors are keyed by the input text so tests can control which
    research questions are considered semantically similar.
    """

    def __init__(self) -> None:
        self.is_mock = False
        self.vectors: dict[str, list[float]] = {
            "PCA 是否提升分类准确率？": [1.0, 0.0],
            "分类准确率是否可以通过 PCA 提升？": [0.95, 0.31],
            "社交媒体使用是否促进青年政治参与？": [1.0, 0.0],
            "社交媒体对青年政治参与有何影响？": [0.96, 0.28],
            "央行数字货币对货币政策传导机制的影响": [0.0, 1.0],
            "Q1": [1.0, 0.0],
            "Q2": [0.0, 1.0],
        }

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors.get(text, [0.0, 0.0]).copy() for text in texts]


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
    with patch(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            embedding_client=_FakeEmbeddingClient(),
        )
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
    with patch(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["hss-001", "hss-002"],
            embedding_client=_FakeEmbeddingClient(),
        )
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
    insight = await build_claim_evolution_insight(
        graphs,
        ["hss-001", "hss-002"],
        embedding_client=_FakeEmbeddingClient(),
    )
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
    with patch(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["hss-001", "hss-002"],
            embedding_client=_FakeEmbeddingClient(),
        )
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
    # LLM recognizes identical claims as inheritance, so it still returns READY.
    # The evolution_type should be inherit and problem_fit_score should be high.
    with patch(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=AsyncMock(
            evolution_type="inherit",
            problem_fit_score=95,
            comparison_summary="两篇论文结论一致，均认为 PCA 可提升分类准确率。",
            evidence_summary=None,
        ),
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            embedding_client=_FakeEmbeddingClient(),
        )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert point.evolution_type == EvolutionType.INHERIT
    assert point.problem_fit_score == 95


async def test_claim_evolution_ready_when_token_overlap_above_threshold() -> None:
    """Questions do not need to be identical; sufficient semantic overlap is enough."""
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
    with patch(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            embedding_client=_FakeEmbeddingClient(),
        )
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


async def test_claim_evolution_backfills_missing_claims_from_vector_store() -> None:
    """When both papers lack Claim nodes, VectorStore chunks are used as claim context."""
    from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = [
        AsyncMock(text="实验结果显示准确率提升 5%。"),
        AsyncMock(text="进一步分析表明提升具有统计显著性。"),
    ]

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
    with patch(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            vector_store=vector_store,
            embedding_client=_FakeEmbeddingClient(),
        )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert "实验结果显示准确率提升 5%" in (point.paper_a_claim or "")
    assert "实验结果显示准确率提升 5%" in (point.paper_b_claim or "")
    vector_store.query_chunks.assert_awaited()


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
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_summary:
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            vector_store=vector_store,
            embedding_client=_FakeEmbeddingClient(),
        )
    assert insight is not None
    # Query is now graph-topology-guided: the aligned question label is the anchor.
    expected_query = "PCA 是否提升分类准确率？ 结论 证据 实验设计 差异"
    vector_store.query_chunks.assert_any_await(expected_query, paper_id="stem-001", top_k=3)
    vector_store.query_chunks.assert_any_await(expected_query, paper_id="stem-002", top_k=3)
    assert mock_summary.called
    context = mock_summary.call_args.args[0]
    assert "claim chunk for stem-001" in context
    assert "another claim chunk for stem-001" in context


async def test_claim_evolution_llm_structured_output_populates_fields() -> None:
    """LLM NLI output fills evolution_type, problem_fit_score and evidence_summary."""
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
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=AsyncMock(
            evolution_type="contradict",
            problem_fit_score=88,
            comparison_summary="两篇论文结论存在分歧。",
            evidence_summary="A 认为提升 5%，B 认为无显著变化。",
        ),
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            embedding_client=_FakeEmbeddingClient(),
        )
    assert insight is not None
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert point.evolution_type == EvolutionType.CONTRADICT
    assert point.problem_fit_score == 88
    assert point.evidence_summary == "A 认为提升 5%，B 认为无显著变化。"
