# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit: frozen classifier_heuristic_fallback code vs user toast message separation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.agents.classifier_heuristic import classify_heuristic

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)

FROZEN_CODE = "classifier_heuristic_fallback"
FROZEN_MESSAGE = "触发分类启发式Fallback!"


def test_g_frozen_constants_exact_values() -> None:
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE == FROZEN_CODE
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE == FROZEN_MESSAGE


@pytest.mark.asyncio
async def test_g_fallback_warning_is_machine_code_not_user_message(live_classify_env: None) -> None:
    _ = live_classify_env
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await classify(STEM_SAMPLE)

    assert result.warnings == [FROZEN_CODE]
    assert FROZEN_MESSAGE not in result.warnings
    assert all(isinstance(code, str) for code in result.warnings)


@pytest.mark.asyncio
async def test_g_fallback_classification_reason_is_heuristic_not_toast(live_classify_env: None) -> None:
    """ParadigmClassification.reason keeps rule-layer explanation; toast uses classify_warnings."""
    _ = live_classify_env
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await classify(STEM_SAMPLE)

    heuristic = classify_heuristic(STEM_SAMPLE)
    assert result.classification.reason == heuristic.reason
    assert result.classification.reason != FROZEN_MESSAGE
    assert FROZEN_MESSAGE not in result.classification.reason


@pytest.mark.asyncio
async def test_g_llm_success_has_no_classify_warnings(live_classify_env: None) -> None:
    from backend.schemas.paradigm import Paradigm, ParadigmClassification

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

    assert result.warnings == []
    assert FROZEN_CODE not in result.warnings
