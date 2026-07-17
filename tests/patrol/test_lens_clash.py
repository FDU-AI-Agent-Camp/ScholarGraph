# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for lens_clash detection."""

from unittest.mock import AsyncMock, patch

from backend.patrol.lens_clash import (
    LENS_CLASH_INSIGHT_ID,
    LENS_CLASH_TITLE,
    analytical_lens_nodes,
    build_lens_clash_insight,
)
from backend.schemas.patrol import LensClashPoint
from tests.helpers.patrol_graphs import build_hss_graph_with_lens


def test_analytical_lens_nodes_filters_by_type() -> None:
    graph = build_hss_graph_with_lens("hss-001", lens_id="n_lens", lens_label="历史制度主义")
    lenses = analytical_lens_nodes(graph)
    assert len(lenses) == 1
    assert lenses[0].label == "历史制度主义"


async def test_build_lens_clash_insight_with_different_lenses() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_lens("hss-001", lens_id="n_lens_a", lens_label="消费社会"),
        "hss-002": build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label="公共领域"),
    }
    insight = await build_lens_clash_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.insight_id == LENS_CLASH_INSIGHT_ID
    assert insight.title == LENS_CLASH_TITLE
    assert "消费社会" in insight.summary
    assert "公共领域" in insight.summary
    assert [ref.node_id for ref in insight.node_refs] == ["n_lens_a", "n_lens_b"]
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, LensClashPoint)
    assert point.mode == "lens_clash"
    assert point.lens_a == "消费社会"
    assert point.lens_b == "公共领域"
    assert point.clash_aspect == "analytical_framework"


async def test_build_lens_clash_insight_returns_none_without_lenses() -> None:
    graph = build_hss_graph_with_lens("hss-001", lens_id="n_lens", lens_label="历史制度主义")
    graph.nodes = [node for node in graph.nodes if node.type != "AnalyticalLens"]
    graphs = {
        "hss-001": graph,
        "hss-002": build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label="公共领域"),
    }
    assert await build_lens_clash_insight(graphs, ["hss-001", "hss-002"]) is None


async def test_build_lens_clash_insight_same_lens_summary() -> None:
    label = "历史制度主义"
    graphs = {
        "hss-001": build_hss_graph_with_lens("hss-001", lens_id="n_lens_a", lens_label=label),
        "hss-002": build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label=label),
    }
    insight = await build_lens_clash_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert "未检出显著学派冲突" in insight.summary
    point = insight.structured_points[0]
    assert isinstance(point, LensClashPoint)
    assert point.clash_aspect == "none"


async def test_build_lens_clash_insight_uses_first_lens_when_multiple() -> None:
    from backend.schemas.graph import GraphNode

    graph = build_hss_graph_with_lens("hss-001", lens_id="n_lens_primary", lens_label="主视角")
    graph.nodes.append(
        GraphNode(id="n_lens_secondary", label="次视角", type="AnalyticalLens", data={}),
    )
    graphs = {
        "hss-001": graph,
        "hss-002": build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label="公共领域"),
    }
    insight = await build_lens_clash_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.node_refs[0].node_id == "n_lens_primary"
    assert insight.node_refs[0].label == "主视角"


async def test_build_lens_clash_insight_returns_none_for_wrong_paper_count() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_lens("hss-001", lens_id="n_lens", lens_label="A"),
    }
    assert await build_lens_clash_insight(graphs, ["hss-001"]) is None


async def test_build_lens_clash_insight_uses_llm_summary_when_available() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_lens("hss-001", lens_id="n_a", lens_label="A"),
        "hss-002": build_hss_graph_with_lens("hss-002", lens_id="n_b", lens_label="B"),
    }
    llm_text = "LLM 生成的 Lens Clash 摘要：两篇论文在分析视角上存在明显学派差异。"
    with patch(
        "backend.patrol.lens_clash.generate_patrol_summary",
        new_callable=AsyncMock,
        return_value=llm_text,
    ):
        insight = await build_lens_clash_insight(graphs, ["hss-001", "hss-002"])
    assert insight is not None
    assert insight.summary.startswith(llm_text)
