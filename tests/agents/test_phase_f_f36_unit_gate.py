"""F.6 acceptance gate T7–T8: LLM success and heuristic fallback unit paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extract_llm import extract_with_llm
from backend.agents.extract_types import ExtractResult
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import LlmClient, reset_llm_client_cache
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from tests.agents.conftest import minimal_valid_llm_graph
from tests.helpers.f33_hss_graphs import assert_hss_excludes_stem_only_node_types
from tests.helpers.f33_stem_graphs import assert_stem_excludes_hss_only_node_types


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_t7_with_structured_output_success_has_no_extract_warnings(live_extract_env) -> None:
    """T7: mock with_structured_output → valid graph → warnings=[]."""
    _ = live_extract_env
    llm_graph = minimal_valid_llm_graph(paper_id="t7-paper")
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=llm_graph)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    await extract_with_llm(
        "标题：测试\n本文认为……",
        Paradigm.HSS,
        paper_id="t7-paper",
        llm_client=client,
    )
    chat.with_structured_output.assert_called_once_with(UnifiedPaperGraph)

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(return_value=llm_graph),
    ):
        result = await extract("标题：测试\n本文认为……", Paradigm.HSS, paper_id="t7-paper")

    assert isinstance(result, ExtractResult)
    assert result.warnings == []
    assert result.graph.paper_id == "t7-paper"

    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_t8_llm_failure_falls_back_with_extract_heuristic_fallback_code(live_extract_env) -> None:
    """T8: LLM error → heuristic graph + extract_heuristic_fallback."""
    _ = live_extract_env

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await extract(
            "标题：近代口岸研究\n本文认为通商口岸体现制度路径依赖。",
            Paradigm.HSS,
            paper_id="t8-paper",
        )

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paper_id == "t8-paper"
    assert any(node.type == "Thesis" for node in result.graph.nodes)
    assert_hss_excludes_stem_only_node_types(result.graph)


@pytest.mark.asyncio
async def test_t8_stem_llm_failure_falls_back_without_hss_only_types(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await extract(
            "Title: ML\nWe study the task. Method and experiments on dataset with metric.",
            Paradigm.STEM,
            paper_id="t8-stem",
        )

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert_stem_excludes_hss_only_node_types(result.graph)
