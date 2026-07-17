# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paradigm classifier — two-stage LLM with heuristic fallback (Phase G)."""

from __future__ import annotations

import logging

from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.classifier_heuristic import classify_heuristic
from backend.agents.classifier_llm import classify_with_llm
from backend.agents.classifier_types import ClassifyResult
from backend.agents.mock_agents import mock_classify
from backend.config import Settings, get_settings
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError

logger = logging.getLogger(__name__)


def _fallback_to_heuristic(
    classifier_input: str,
    *,
    reason: Exception | str,
) -> ClassifyResult:
    """Degrade to keyword rules and record fallback warning."""
    logger.warning(
        "classify_llm_fallback",
        extra={"reason": str(reason)},
    )
    return ClassifyResult(
        classification=classify_heuristic(classifier_input),
        warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    )


async def _classify_live(classifier_input: str, *, settings: Settings) -> ClassifyResult:
    if not settings.classifier_llm_enabled:
        logger.warning(
            "classify_llm_disabled",
            extra={"reason": "classifier_llm_disabled"},
        )
        return _fallback_to_heuristic(classifier_input, reason="classifier_llm_disabled")

    try:
        classification = await classify_with_llm(classifier_input, settings=settings)
    except Exception as exc:
        if not settings.classifier_heuristic_fallback:
            raise ServiceError(PIPELINE_FAILED_CODE, f"范式 LLM 分类失败: {exc}") from exc
        return _fallback_to_heuristic(classifier_input, reason=exc)

    return ClassifyResult(classification=classification, warnings=[])


async def classify(classifier_input: str) -> ClassifyResult:
    """Classify a paper snippet; live mode prefers two-stage LLM with heuristic fallback."""
    settings = get_settings()
    if settings.is_llm_mock:
        return ClassifyResult(classification=mock_classify(classifier_input), warnings=[])

    if not classifier_input or not classifier_input.strip():
        raise ValueError("classifier_input must be a non-empty string.")

    return await _classify_live(classifier_input, settings=settings)
