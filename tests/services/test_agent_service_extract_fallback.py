# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Service layer: AgentService passes through heuristic fallback without failing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError


@pytest.fixture
def live_extract_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_extract_graph_returns_fallback_result_without_service_error(live_extract_env: None) -> None:
    _ = live_extract_env
    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await AgentService().extract_graph(
            "标题：测试\n本文认为……",
            Paradigm.HSS,
            paper_id="svc-fallback-001",
        )

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.graph.paper_id == "svc-fallback-001"
    assert result.graph.nodes


@pytest.mark.asyncio
async def test_extract_graph_fallback_disabled_raises_pipeline_failed(
    live_extract_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = live_extract_env
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()

    with (
        patch(
            "backend.agents.extractor.extract_with_llm",
            new=AsyncMock(side_effect=ValueError("schema invalid")),
        ),
        pytest.raises(ServiceError) as err,
    ):
        await AgentService().extract_graph("body", Paradigm.HSS, paper_id="svc-no-fallback")

    assert err.value.code == "PIPELINE_FAILED"

    get_settings.cache_clear()
    reset_llm_client_cache()
