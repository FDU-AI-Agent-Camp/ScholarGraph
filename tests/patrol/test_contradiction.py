"""Unit tests for contradiction patrol strategy."""

from unittest.mock import AsyncMock, patch

from backend.patrol.contradiction import (
    CONTRADICTION_INSIGHT_ID,
    CONTRADICTION_TITLE,
    build_contradiction_insight,
    sub_argument_nodes,
    thesis_nodes,
)
from backend.schemas.patrol import PatrolMode
from tests.helpers.patrol_graphs import build_hss_graph_with_thesis


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
    assert "夏尔巴" in insight.summary or "电影" in insight.summary
    assert [ref.node_id for ref in insight.node_refs] == ["n_t_a", "n_t_b"]


async def test_build_contradiction_insight_uses_llm_summary() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_thesis("hss-001", thesis_id="n_a", thesis_label="论点 A"),
        "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="论点 B"),
    }
    llm_text = "LLM 生成的 Contradiction 摘要：两篇论文在核心论点上存在显著张力。"
    with patch(
        "backend.patrol.contradiction.generate_patrol_summary",
        new_callable=AsyncMock,
        return_value=llm_text,
    ):
        insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.summary == llm_text


def test_sub_argument_nodes_collected() -> None:
    graph = build_hss_graph_with_thesis(
        "hss-001",
        thesis_id="n_t",
        thesis_label="核心",
        sub_arguments=[("n_s1", "分论点一")],
    )
    assert len(sub_argument_nodes(graph)) == 1


async def test_build_contradiction_insight_returns_none_without_thesis() -> None:
    graph = build_hss_graph_with_thesis("hss-001", thesis_id="n_t", thesis_label="A")
    graph.nodes = [node for node in graph.nodes if node.type != "Thesis"]
    assert (
        await build_contradiction_insight(
            {"hss-001": graph, "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="B")},
            ["hss-001", "hss-002"],
        )
        is None
    )


async def test_build_contradiction_insight_same_thesis_uses_fallback() -> None:
    label = "相同核心论点"
    graphs = {
        "hss-001": build_hss_graph_with_thesis("hss-001", thesis_id="n_a", thesis_label=label),
        "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label=label),
    }
    insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert "未检出显著论证矛盾" in insight.summary


async def test_build_contradiction_insight_returns_none_for_wrong_paper_count() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_thesis("hss-001", thesis_id="n_t", thesis_label="A"),
    }
    assert await build_contradiction_insight(graphs, ["hss-001"]) is None


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


async def test_build_contradiction_uses_first_thesis_when_multiple() -> None:
    from backend.schemas.graph import GraphNode

    graph = build_hss_graph_with_thesis("hss-001", thesis_id="n_primary", thesis_label="主论点")
    graph.nodes.append(GraphNode(id="n_secondary", label="次论点", type="Thesis", data={}))
    graphs = {
        "hss-001": graph,
        "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="B"),
    }
    insight = await build_contradiction_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.node_refs[0].node_id == "n_primary"
