"""Unit tests for claim_evolution patrol mode."""

import math
from unittest.mock import AsyncMock, patch

import pytest
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
from tests.patrol.conftest import patch_patrol_settings


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


async def test_claim_evolution_chunk_top_k_is_configurable(monkeypatch) -> None:
    """PATROL_CLAIM_CHUNK_TOP_K must control how many chunks are backfilled into the prompt."""
    from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    patch_patrol_settings(monkeypatch, patrol_claim_chunk_top_k=5)

    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = [AsyncMock(text=f"chunk {i} for missing claim") for i in range(5)]

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
    ) as mock_summary:
        insight = await build_claim_evolution_insight(
            graphs,
            ["stem-001", "stem-002"],
            vector_store=vector_store,
            embedding_client=_FakeEmbeddingClient(),
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    vector_store.query_chunks.assert_any_await("Q1", paper_id="stem-001", top_k=5)
    vector_store.query_chunks.assert_any_await("Q1", paper_id="stem-002", top_k=5)
    context = mock_summary.call_args.args[0]
    for i in range(5):
        assert f"chunk {i} for missing claim" in context


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
    # When vector_store is supplied and exists() returns True, no degradation flag is set.
    assert "patrol_rag_context_degraded" not in insight.meta
    assert mock_summary.called
    context = mock_summary.call_args.args[0]
    assert "claim chunk for stem-001" in context
    assert "another claim chunk for stem-001" in context


async def test_claim_evolution_records_rag_degradation_when_index_missing() -> None:
    """If VectorStore index is missing, READY insight carries patrol_rag_context_degraded meta."""
    vector_store = AsyncMock()
    vector_store.exists.return_value = False
    vector_store.query_chunks.return_value = []
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
            vector_store=vector_store,
            embedding_client=_FakeEmbeddingClient(),
        )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.meta.get("patrol_rag_context_degraded", {}).get("reason") == "index_not_ready"
    assert set(insight.meta["patrol_rag_context_degraded"]["paper_ids"]) == {"stem-001", "stem-002"}


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


async def test_claim_evolution_insufficient_when_no_claims_and_no_chunks() -> None:
    """Both papers lack Claim nodes and VectorStore returns nothing -> INSUFFICIENT_DATA."""
    from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = []

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
    insight = await build_claim_evolution_insight(
        graphs,
        ["stem-001", "stem-002"],
        vector_store=vector_store,
        embedding_client=_FakeEmbeddingClient(),
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
    assert "未检出明确结论" in insight.summary


async def test_claim_evolution_english_questions_use_lower_threshold(monkeypatch) -> None:
    """English paraphrases around 0.71 cosine should pass the relaxed RQ gate."""
    from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=False,
        patrol_claim_rq_threshold=0.75,
        patrol_claim_rq_threshold_english=0.55,
    )

    class _EnglishEmbeddingClient:
        is_mock = False

        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [
                [1.0, 0.0, 0.0],
                [0.71, 0.71, 0.0],
            ]

    left_question = "Does PCA improve classification accuracy on benchmark datasets?"
    right_question = "Can principal component analysis boost classifier performance?"

    graphs = {
        "stem-001": UnifiedPaperGraph(
            paper_id="stem-001",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(id="n_q", label=left_question, type=NodeType.RESEARCH_QUESTION, data={}),
                GraphNode(id="n_c", label="Accuracy improves by 5%", type=NodeType.CLAIM, data={}),
            ],
            edges=[],
        ),
        "stem-002": UnifiedPaperGraph(
            paper_id="stem-002",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(id="n_q", label=right_question, type=NodeType.RESEARCH_QUESTION, data={}),
                GraphNode(id="n_c", label="No significant change", type=NodeType.CLAIM, data={}),
            ],
            edges=[],
        ),
    }
    insight = await build_claim_evolution_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=_EnglishEmbeddingClient(),
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY


_MACRO_SOCIAL_LABEL = "社交媒体与政治参与的关系研究"
_MICRO_WEIBO_LABEL = "微博使用对投票率的影响"
_MACRO_MICRO_COSINE = 0.75
_MICRO_VECTOR = [_MACRO_MICRO_COSINE, math.sqrt(1.0 - _MACRO_MICRO_COSINE**2)]


class _MacroMicroGranularityEmbeddingClient:
    """High bi-encoder cosine but semantically misaligned macro vs micro questions."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: dict[str, list[float]] = {
            _MACRO_SOCIAL_LABEL: [1.0, 0.0],
            _MICRO_WEIBO_LABEL: _MICRO_VECTOR.copy(),
            "社交媒体使用是否促进青年政治参与？": [1.0, 0.0],
            "社交媒体对青年政治参与有何影响？": [0.96, 0.28],
        }
        return [vectors.get(text, [0.0, 0.0]).copy() for text in texts]


class _MockPatrolRerankerClient:
    """Deterministic rerank scores keyed by (left_label, right_label)."""

    def __init__(self, scores: dict[tuple[str, str], float]) -> None:
        self._scores = scores

    async def rerank_pair(self, text_a: str, text_b: str) -> float:
        return self._scores.get((text_a, text_b), 0.0)

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [await self.rerank_pair(left, right) for left, right in pairs]


async def test_claim_evolution_rerank_blocks_macro_micro_granularity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """卡点：粗筛放行但 Cross-Encoder 精排拦截宏微观粒度不平行的误配对。"""
    from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )

    graphs = {
        "hss-macro": UnifiedPaperGraph(
            paper_id="hss-macro",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n_thesis", label=_MACRO_SOCIAL_LABEL, type=NodeType.THESIS, data={}),
                GraphNode(id="n_claim", label="社交媒体显著提升政治参与", type=NodeType.CLAIM, data={}),
            ],
            edges=[],
        ),
        "hss-micro": UnifiedPaperGraph(
            paper_id="hss-micro",
            paradigm=Paradigm.HSS,
            nodes=[
                GraphNode(id="n_thesis", label=_MICRO_WEIBO_LABEL, type=NodeType.THESIS, data={}),
                GraphNode(id="n_claim", label="微博投票率略有提升", type=NodeType.CLAIM, data={}),
            ],
            edges=[],
        ),
    }
    reranker = _MockPatrolRerankerClient(
        {
            (_MACRO_SOCIAL_LABEL, _MICRO_WEIBO_LABEL): 0.45,
            (_MICRO_WEIBO_LABEL, _MACRO_SOCIAL_LABEL): 0.45,
        }
    )
    insight = await build_claim_evolution_insight(
        graphs,
        ["hss-macro", "hss-micro"],
        embedding_client=_MacroMicroGranularityEmbeddingClient(),
        reranker_client=reranker,
    )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []


async def test_claim_evolution_two_stage_pipeline_passes_with_rerank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """卡点：粗筛 + Cross-Encoder 精排均通过后进入 READY 下游。"""
    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )

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
    reranker = _MockPatrolRerankerClient(
        {
            (
                "社交媒体使用是否促进青年政治参与？",
                "社交媒体对青年政治参与有何影响？",
            ): 0.82,
            (
                "社交媒体对青年政治参与有何影响？",
                "社交媒体使用是否促进青年政治参与？",
            ): 0.82,
        }
    )
    with patch(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        insight = await build_claim_evolution_insight(
            graphs,
            ["hss-001", "hss-002"],
            embedding_client=_MacroMicroGranularityEmbeddingClient(),
            reranker_client=reranker,
        )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    assert "社交媒体" in point.research_question


class _ClaimEvolutionFailingEmbeddingClient:
    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding endpoint unavailable")


@pytest.mark.asyncio
async def test_claim_evolution_rq_gate_embedding_failure_returns_insufficient_data() -> None:
    """Embedding outage must degrade to INSUFFICIENT_DATA instead of bubbling 500."""
    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
        "stem-002": build_stem_graph_with_question_claim(
            "stem-002",
            question_label="PCA 能否提高分类精度？",
            claim_label="准确率无显著变化",
        ),
    }
    insight = await build_claim_evolution_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=_ClaimEvolutionFailingEmbeddingClient(),
    )

    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.structured_points == []
