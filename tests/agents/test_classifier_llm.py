"""Unit tests for classifier LLM primary path (Phase G)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.agents.classifier_llm import (
    CLASSIFIER_PROMPT_PATH,
    _validate_llm_classification,
    classify_with_llm,
    load_classifier_prompt,
)
from backend.llm.client import LlmClient
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from pydantic import ValidationError

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


def test_load_classifier_prompt_reads_markdown_file() -> None:
    prompt = load_classifier_prompt()
    assert CLASSIFIER_PROMPT_PATH.is_file()
    assert "STEM" in prompt
    assert "HSS" in prompt
    assert len(prompt.strip()) > 50


def test_validate_llm_classification_rejects_empty_reason() -> None:
    classification = ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="   ")
    with pytest.raises(ValueError, match="reason is empty"):
        _validate_llm_classification(classification)


def test_paradigm_classification_pydantic_bounds() -> None:
    with pytest.raises(ValidationError):
        ParadigmClassification(paradigm=Paradigm.STEM, confidence=-0.01, reason="ok")
    with pytest.raises(ValidationError):
        ParadigmClassification(paradigm=Paradigm.HSS, confidence=1.01, reason="ok")


@pytest.mark.asyncio
async def test_classify_with_llm_raises_when_both_models_fail(live_classify_env: None) -> None:
    _ = live_classify_env
    primary_runnable = MagicMock()
    primary_runnable.ainvoke = AsyncMock(side_effect=RuntimeError("primary failed"))
    fallback_runnable = MagicMock()
    fallback_runnable.ainvoke = AsyncMock(side_effect=RuntimeError("fallback failed"))

    primary_chat = MagicMock()
    primary_chat.with_structured_output.return_value = primary_runnable
    fallback_chat = MagicMock()
    fallback_chat.with_structured_output.return_value = fallback_runnable

    client = LlmClient()
    client._chat = primary_chat
    client._fallback_chat = fallback_chat

    with pytest.raises(RuntimeError, match="fallback failed"):
        await classify_with_llm(STEM_SAMPLE, llm_client=client)


@pytest.mark.asyncio
async def test_classify_with_llm_primary_success(live_classify_env: None) -> None:
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.92,
        reason="Benchmark and dataset paper.",
    )
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=expected)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    result = await classify_with_llm(STEM_SAMPLE, llm_client=client)

    assert result.paradigm == Paradigm.STEM
    chat.with_structured_output.assert_called_once_with(ParadigmClassification)


@pytest.mark.asyncio
async def test_classify_with_llm_retries_fallback_model(live_classify_env: None) -> None:
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.88,
        reason="Theory-driven qualitative study.",
    )
    primary_runnable = MagicMock()
    primary_runnable.ainvoke = AsyncMock(side_effect=RuntimeError("primary failed"))
    fallback_runnable = MagicMock()
    fallback_runnable.ainvoke = AsyncMock(return_value=expected)

    primary_chat = MagicMock()
    primary_chat.with_structured_output.return_value = primary_runnable
    fallback_chat = MagicMock()
    fallback_chat.with_structured_output.return_value = fallback_runnable

    client = LlmClient()
    client._chat = primary_chat
    client._fallback_chat = fallback_chat

    result = await classify_with_llm(
        "Title: Historical ethnography. We analyze archives and interviews.",
        llm_client=client,
    )

    assert result.paradigm == Paradigm.HSS
    primary_chat.with_structured_output.assert_called_once()
    fallback_chat.with_structured_output.assert_called_once()
