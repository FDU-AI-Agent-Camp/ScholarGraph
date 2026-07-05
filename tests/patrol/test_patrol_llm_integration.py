"""Integration: run_patrol with injected LLM client (both modes)."""

from unittest.mock import AsyncMock, MagicMock

from backend.graph.store import GraphStore
from backend.patrol.service import run_patrol
from backend.schemas.patrol import PatrolInsightStatus, PatrolMode
from backend.schemas.patrol_llm import PatrolSummaryOutput
from tests.helpers.patrol_graphs import build_hss_graph_with_lens, build_hss_graph_with_thesis, seed_patrol_graphs


def _mock_llm_client(summary: str) -> MagicMock:
    mock_client = MagicMock()
    mock_structured = AsyncMock()
    mock_structured.ainvoke.return_value = PatrolSummaryOutput(summary=summary)
    mock_client.chat.with_structured_output.return_value = mock_structured
    return mock_client


async def test_run_patrol_lens_clash_with_structured_llm(tmp_path) -> None:
    store_dir = tmp_path / "graphs"
    seed_patrol_graphs(
        store_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    llm_summary = "集成 LLM 摘要：两篇论文的分析视角分别偏向消费社会与公共领域，存在学派张力。"
    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.LENS_CLASH,
        store=GraphStore(base_dir=store_dir),
        llm_client=_mock_llm_client(llm_summary),
    )
    assert report.insights[0].summary == llm_summary


async def test_run_patrol_contradiction_with_structured_llm() -> None:
    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_a",
            thesis_label="论点 A",
            sub_arguments=[("n_sub_a", "分论点 A")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_b",
            thesis_label="论点 B",
            sub_arguments=[("n_sub_b", "分论点 B")],
        ),
    }
    llm_summary = "集成 LLM 摘要：两篇论文的核心论点在证据链与解释框架上存在潜在矛盾。"
    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.CONTRADICTION,
        graph_loader=graphs.get,
        llm_client=_mock_llm_client(llm_summary),
    )
    assert report.mode == PatrolMode.CONTRADICTION
    assert report.insights[0].status == PatrolInsightStatus.READY
    assert report.insights[0].summary == llm_summary


async def test_run_patrol_llm_fallback_to_template_when_client_raises() -> None:
    mock_client = MagicMock()
    mock_structured = AsyncMock()
    mock_structured.ainvoke.side_effect = RuntimeError("llm down")
    mock_client.chat.with_structured_output.return_value = mock_structured
    graphs = {
        "hss-001": build_hss_graph_with_lens("hss-001", lens_id="n_a", lens_label="消费社会"),
        "hss-002": build_hss_graph_with_lens("hss-002", lens_id="n_b", lens_label="公共领域"),
    }
    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.LENS_CLASH,
        graph_loader=graphs.get,
        llm_client=mock_client,
    )
    assert "消费社会" in report.insights[0].summary
    assert "公共领域" in report.insights[0].summary
