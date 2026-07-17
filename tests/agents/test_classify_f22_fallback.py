# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase G acceptance: classifier LLM fallback (G2.1–G2.5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)
HSS_SAMPLE = "标题：平台零工经济与劳动者心理。本文通过访谈材料和公共领域理论视角，分析劳动者经验。"


@pytest.mark.asyncio
async def test_llm_success_has_no_classify_warnings(live_classify_env: None) -> None:
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.91,
        reason="Quantitative benchmark paper.",
    )
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(return_value=expected),
    ):
        result = await classify(STEM_SAMPLE)

    assert result.classification.paradigm == Paradigm.STEM
    assert result.warnings == []


@pytest.mark.asyncio
async def test_llm_failure_triggers_heuristic_fallback(live_classify_env: None) -> None:
    _ = live_classify_env
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await classify(STEM_SAMPLE)

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.classification.paradigm == Paradigm.STEM


@pytest.mark.asyncio
async def test_classifier_llm_disabled_triggers_heuristic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_heuristic_fallback_classifies_hss_sample(live_classify_env: None) -> None:
    _ = live_classify_env
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await classify(HSS_SAMPLE)

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.classification.paradigm == Paradigm.HSS


@pytest.mark.asyncio
async def test_no_heuristic_fallback_raises_service_error(
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
async def test_mock_mode_never_calls_live_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert result.warnings == []
