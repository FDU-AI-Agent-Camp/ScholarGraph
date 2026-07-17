# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase G.2 acceptance: env switches G2.4 (LLM disabled) and G2.5 (no fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm
from backend.services.errors import ServiceError

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.mark.asyncio
async def test_g24_classifier_llm_disabled_skips_live_llm_and_writes_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
async def test_g25_heuristic_fallback_disabled_raises_pipeline_failed(
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
