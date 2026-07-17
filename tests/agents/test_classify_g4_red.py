# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
G.4 红灯：LLM_MODE 与 classify 能力点边界。

运行：uv run pytest -m red tests/agents/test_classify_g4_red.py -rx
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.services.errors import ServiceError

pytestmark = pytest.mark.red

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.mark.asyncio
async def test_red_mock_mode_never_calls_classify_with_llm_even_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert result.warnings == []


@pytest.mark.asyncio
async def test_red_mock_mode_must_not_emit_classifier_heuristic_fallback_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    result = await classify(STEM_SAMPLE)

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE not in result.warnings


@pytest.mark.asyncio
async def test_red_live_without_heuristic_fallback_raises_on_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        with pytest.raises(ServiceError) as err:
            await classify(STEM_SAMPLE)

    assert err.value.code == "PIPELINE_FAILED"


@pytest.mark.asyncio
async def test_red_live_classifier_llm_disabled_must_not_call_classify_with_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
