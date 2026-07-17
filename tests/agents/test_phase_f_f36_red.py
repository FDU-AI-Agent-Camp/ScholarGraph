# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
F.6 红灯：图谱抽取门禁边界

运行：uv run pytest -m red tests/agents/test_phase_f_f36_red.py -q
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError

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
@pytest.mark.asyncio
async def test_red_t7_success_path_must_not_emit_fallback_warning(live_extract_env) -> None:
    _ = live_extract_env
    from tests.agents.conftest import minimal_valid_llm_graph

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(return_value=minimal_valid_llm_graph(paper_id="red-t7")),
    ):
        result = await extract("标题：测试\n本文认为……", Paradigm.HSS, paper_id="red-t7")

    assert result.warnings == []
    assert EXTRACT_HEURISTIC_FALLBACK_CODE not in result.warnings


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_t8_fallback_disabled_raises_not_warning(live_extract_env, monkeypatch) -> None:
    _ = live_extract_env
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("llm down")),
    ):
        with pytest.raises(ServiceError) as err:
            await AgentService().extract_graph("body", Paradigm.HSS, paper_id="red-t8-fail")

    assert err.value.code == "PIPELINE_FAILED"

    get_settings.cache_clear()


@pytest.mark.red
@pytest.mark.asyncio
async def test_red_t8_empty_llm_graph_must_fallback_not_succeed_silently(live_extract_env) -> None:
    _ = live_extract_env

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=ValueError("LLM graph has no nodes.")),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-empty-graph")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.nodes
