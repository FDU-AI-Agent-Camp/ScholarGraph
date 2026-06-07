"""
F.3 红灯测试（STEM 节点/边边界 + HSS 禁止 STEM type 交叉）

运行：uv run pytest -m red tests/agents/test_extract_f33_stem_red.py tests/agents/test_extract_f33_red.py -q
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

from tests.helpers.f33_stem_graphs import minimal_f33_stem_graph

pytestmark = pytest.mark.red

HSS_ONLY_NODE_TYPES = (
    "Thesis",
    "SubArgument",
    "AnalyticalLens",
    "IntellectualContext",
    "ObjectOrData",
)


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.red
@pytest.mark.parametrize("hss_only_type", HSS_ONLY_NODE_TYPES)
def test_red_f33_stem_schema_rejects_hss_only_node_type(hss_only_type: str) -> None:
    base = minimal_f33_stem_graph()
    with pytest.raises(ValidationError, match="forbidden node types"):
        UnifiedPaperGraph(
            paper_id=base.paper_id,
            paradigm=Paradigm.STEM,
            nodes=[
                *base.nodes,
                GraphNode(id=f"n_{hss_only_type.lower()}", label="hss node", type=hss_only_type),
            ],
            edges=base.edges,
        )


@pytest.mark.red
def test_red_f33_stem_schema_rejects_sub_argument_of_edge() -> None:
    base = minimal_f33_stem_graph()
    with pytest.raises(ValidationError, match="forbidden edge types"):
        UnifiedPaperGraph(
            paper_id=base.paper_id,
            paradigm=Paradigm.STEM,
            nodes=base.nodes,
            edges=[
                *base.edges,
                GraphEdge(
                    id="e_bad",
                    source="n_method",
                    target="n_question",
                    label="SUB_ARGUMENT_OF",
                    type="SUB_ARGUMENT_OF",
                ),
            ],
        )


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_f33_stem_llm_thesis_node_triggers_fallback(live_extract_env: None) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extract_llm._invoke_structured",
        new=AsyncMock(side_effect=ValueError("STEM graph contains forbidden node types: ['Thesis']")),
    ):
        result = await extract("Title: test\nMethod and benchmark.", Paradigm.STEM, paper_id="f33-red-stem-thesis")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert all(node.type != "Thesis" for node in result.graph.nodes)
