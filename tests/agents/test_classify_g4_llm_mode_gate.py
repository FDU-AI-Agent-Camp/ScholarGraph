"""G.4 unit gate: LLM_MODE mock/live × CLASSIFIER_LLM_ENABLED / CLASSIFIER_HEURISTIC_FALLBACK."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.mock_agents import mock_classify
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm
from backend.services.agent_service import AgentService
from backend.services.errors import ServiceError

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.fixture
def mock_classify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.fixture
def live_classify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_g4_mock_mode_uses_mock_classify_without_live_llm(mock_classify_env: None) -> None:
    _ = mock_classify_env
    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert result.warnings == []
    assert result.classification == mock_classify(STEM_SAMPLE)


@pytest.mark.asyncio
async def test_g4_mock_mode_ignores_classifier_llm_disabled_flag(
    mock_classify_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM_MODE=mock wins over CLASSIFIER_LLM_ENABLED=false — still mock_classify, no warnings."""
    _ = mock_classify_env
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    get_settings.cache_clear()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert result.warnings == []
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE not in result.warnings


@pytest.mark.asyncio
async def test_g4_live_classifier_llm_disabled_skips_live_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.classification.paradigm == Paradigm.STEM


@pytest.mark.asyncio
async def test_g4_live_llm_failure_respects_heuristic_fallback_switch(
    live_classify_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = live_classify_env
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
async def test_g4_agent_service_mock_mode_delegates_without_warnings(mock_classify_env: None) -> None:
    _ = mock_classify_env
    service = AgentService()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await service.classify_paradigm(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert result.warnings == []
    assert result.classification.paradigm == Paradigm.STEM
