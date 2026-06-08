"""
F.3 红灯测试（HSS 节点/边边界）

运行：uv run pytest -m red tests/agents/test_extract_f33_red.py -rx
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from pydantic import ValidationError
from tests.helpers.f33_hss_graphs import F33_FORBIDDEN_STEM_NODE_TYPES, minimal_f33_hss_graph

pytestmark = pytest.mark.red


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.red
def test_red_f33_hss_schema_rejects_research_question_node() -> None:
    base = minimal_f33_hss_graph()
    with pytest.raises(ValidationError, match="forbidden node types"):
        UnifiedPaperGraph(
            paper_id=base.paper_id,
            paradigm=Paradigm.HSS,
            nodes=[
                *base.nodes,
                GraphNode(id="n_rq", label="研究问题", type="ResearchQuestion"),
            ],
            edges=base.edges,
        )


@pytest.mark.red
def test_red_f33_hss_schema_rejects_evaluated_on_edge() -> None:
    base = minimal_f33_hss_graph()
    with pytest.raises(ValidationError, match="forbidden edge types"):
        UnifiedPaperGraph(
            paper_id=base.paper_id,
            paradigm=Paradigm.HSS,
            nodes=base.nodes,
            edges=[
                *base.edges,
                GraphEdge(
                    id="e_bad",
                    source="n_object",
                    target="n_thesis",
                    label="EVALUATED_ON",
                    type="EVALUATED_ON",
                ),
            ],
        )


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_f33_hss_llm_stem_edge_triggers_fallback(live_extract_env: None) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=ValueError("HSS graph contains forbidden edge types: ['ADDRESSES']")),
    ):
        result = await extract("标题：测试\n本文认为……", Paradigm.HSS, paper_id="f33-red-stem-edge")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paradigm == Paradigm.HSS


@pytest.mark.red
@pytest.mark.parametrize("stem_only_type", sorted(F33_FORBIDDEN_STEM_NODE_TYPES))
@pytest.mark.asyncio
async def test_red_f33_hss_llm_stem_only_node_triggers_fallback(
    live_extract_env: None,
    stem_only_type: str,
) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(
            side_effect=ValueError(f"HSS graph contains forbidden node types: ['{stem_only_type}']"),
        ),
    ):
        result = await extract(
            "标题：测试\n本文认为……",
            Paradigm.HSS,
            paper_id=f"f33-red-stem-node-{stem_only_type.lower()}",
        )

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    from tests.helpers.f33_hss_graphs import assert_hss_excludes_stem_only_node_types

    assert_hss_excludes_stem_only_node_types(result.graph)


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_f33_hss_llm_duplicate_node_ids_triggers_fallback(live_extract_env: None) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=ValueError("Graph node ids must be unique.")),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="f33-red-dup-ids")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.nodes


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_f33_hss_llm_dangling_edge_triggers_fallback(live_extract_env: None) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=ValueError("Graph edge e1 references missing node.")),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="f33-red-dangling")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_f33_hss_analytical_lens_in_stem_graph_triggers_fallback(live_extract_env: None) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(
            side_effect=ValueError("STEM graph contains forbidden node types: ['AnalyticalLens']"),
        ),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="f33-red-hss-lens-in-stem")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paradigm == Paradigm.HSS
    assert any(node.type == "AnalyticalLens" for node in result.graph.nodes)
