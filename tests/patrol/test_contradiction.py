"""Unit tests for contradiction patrol strategy."""

from unittest.mock import AsyncMock, patch

from backend.patrol.contradiction import (
    CONTRADICTION_INSIGHT_ID,
    CONTRADICTION_TITLE,
    build_contradiction_insight,
    sub_argument_nodes,
    thesis_nodes,
)
from backend.schemas.patrol import ContradictionPoint, PatrolInsightStatus, PatrolMode
from tests.helpers.patrol_graphs import (
    build_hss_graph_with_thesis,
    build_hss_graph_without_thesis,
)


def test_thesis_nodes_filters_by_type() -> None:
    graph = build_hss_graph_with_thesis(
        "hss-001",
        thesis_id="n_t",
        thesis_label="制度路径依赖塑造近代口岸格局",
    )
    assert len(thesis_nodes(graph)) == 1


async def test_build_contradiction_insight_with_different_theses() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_t_a",
            thesis_label="夏尔巴父系源流具有多元融合特征",
            sub_arguments=[("n_sub_a", "分论点：分子证据支持混合来源")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_t_b",
            thesis_label="电影政治传播强化主流意识形态建构",
            sub_arguments=[("n_sub_b", "分论点：叙事策略随政策周期变化")],
        ),
    }
    insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.insight_id == CONTRADICTION_INSIGHT_ID
    assert insight.title == CONTRADICTION_TITLE
    assert insight.status == PatrolInsightStatus.READY
    assert "夏尔巴" in insight.summary or "电影" in insight.summary
    assert [ref.node_id for ref in insight.node_refs] == ["n_t_a", "n_t_b"]
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, ContradictionPoint)
    assert point.mode == "contradiction"
    assert point.point_a == "夏尔巴父系源流具有多元融合特征"
    assert point.point_b == "电影政治传播强化主流意识形态建构"
    assert point.conflict_type == "potential"


async def test_build_contradiction_insight_uses_llm_summary() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_a",
            thesis_label="论点 A",
            sub_arguments=[("n_sub_a", "分论点：证据链 A")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_b",
            thesis_label="论点 B",
            sub_arguments=[("n_sub_b", "分论点：证据链 B")],
        ),
    }
    llm_text = "LLM 生成的 Contradiction 摘要：两篇论文在核心论点上存在显著张力。"
    with patch(
        "backend.patrol.contradiction.generate_patrol_summary",
        new_callable=AsyncMock,
        return_value=llm_text,
    ):
        insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.summary.startswith(llm_text)


def test_sub_argument_nodes_collected() -> None:
    graph = build_hss_graph_with_thesis(
        "hss-001",
        thesis_id="n_t",
        thesis_label="核心",
        sub_arguments=[("n_s1", "分论点一")],
    )
    assert len(sub_argument_nodes(graph)) == 1


async def test_build_contradiction_insight_returns_insufficient_data_without_thesis() -> None:
    graph = build_hss_graph_without_thesis("hss-001")
    insight = await build_contradiction_insight(
        {"hss-001": graph, "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="B")},
        ["hss-001", "hss-002"],
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.has_contradiction is False
    assert "缺乏核心论点" in insight.summary


async def test_build_contradiction_insight_same_thesis_uses_fallback() -> None:
    label = "相同核心论点"
    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_a",
            thesis_label=label,
            sub_arguments=[("n_sub_a", "分论点 A")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_b",
            thesis_label=label,
            sub_arguments=[("n_sub_b", "分论点 B")],
        ),
    }
    insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert "未检出显著论证矛盾" in insight.summary
    point = insight.structured_points[0]
    assert isinstance(point, ContradictionPoint)
    assert point.conflict_type == "none"


async def test_build_contradiction_insight_returns_none_for_wrong_paper_count() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_thesis("hss-001", thesis_id="n_t", thesis_label="A"),
    }
    assert await build_contradiction_insight(graphs, ["hss-001"]) is None


async def test_build_contradiction_insight_returns_insufficient_data_without_subarguments() -> None:
    """When either paper lacks SubArgument nodes, the LLM chain must be skipped."""
    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_t_a",
            thesis_label="论点 A",
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_t_b",
            thesis_label="论点 B",
            sub_arguments=[("n_sub_b", "分论点 B")],
        ),
    }
    with patch(
        "backend.patrol.contradiction.generate_patrol_summary",
        new_callable=AsyncMock,
    ) as mock_gen:
        insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert insight.has_contradiction is False
    assert "缺乏显式子论点" in insight.summary
    assert "hss-001" in insight.summary
    mock_gen.assert_not_awaited()


async def test_build_contradiction_insight_lists_both_papers_when_both_lack_subarguments() -> None:
    """Gatekeeper should mention every paper that lacks SubArgument nodes."""
    graphs = {
        "hss-001": build_hss_graph_with_thesis("hss-001", thesis_id="n_t_a", thesis_label="论点 A"),
        "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_t_b", thesis_label="论点 B"),
    }
    insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert "hss-001" in insight.summary
    assert "hss-002" in insight.summary


async def test_build_contradiction_passes_subargument_context_to_llm() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_t_a",
            thesis_label="论点 A",
            sub_arguments=[("n_sub_a", "分论点：证据链 A")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_t_b",
            thesis_label="论点 B",
            sub_arguments=[("n_sub_b", "分论点：证据链 B")],
        ),
    }
    with patch(
        "backend.patrol.contradiction.generate_patrol_summary",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_gen:
        await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert mock_gen.call_args.args[0] == PatrolMode.CONTRADICTION
    context = mock_gen.call_args.args[1]
    assert "SubArgument" in context
    assert "分论点：证据链 A" in context
    assert "分论点：证据链 B" in context


async def test_build_contradiction_insight_does_not_block_compliant_requests() -> None:
    """A compliant request (Thesis + SubArgument in both papers) must reach the LLM and return ready."""
    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_t_a",
            thesis_label="论点 A",
            sub_arguments=[("n_sub_a", "分论点 A")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_t_b",
            thesis_label="论点 B",
            sub_arguments=[("n_sub_b", "分论点 B")],
        ),
    }
    llm_text = "正常请求未被门控拦截。"
    with patch(
        "backend.patrol.contradiction.generate_patrol_summary",
        new_callable=AsyncMock,
        return_value=llm_text,
    ) as mock_gen:
        insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.summary.startswith(llm_text)
    mock_gen.assert_awaited_once()


async def test_build_contradiction_uses_first_thesis_when_multiple() -> None:
    from backend.schemas.graph import GraphNode

    graph = build_hss_graph_with_thesis(
        "hss-001",
        thesis_id="n_primary",
        thesis_label="主论点",
        sub_arguments=[("n_sub_a", "分论点 A")],
    )
    graph.nodes.append(GraphNode(id="n_secondary", label="次论点", type="Thesis", data={}))
    graphs = {
        "hss-001": graph,
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_b",
            thesis_label="B",
            sub_arguments=[("n_sub_b", "分论点 B")],
        ),
    }
    insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert insight.node_refs[0].node_id == "n_primary"
