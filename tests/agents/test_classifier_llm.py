"""Unit tests for classifier LLM primary path (Phase G)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.classifier_llm import (
    CLASSIFIER_PROFILE_PROMPT_PATH,
    CLASSIFIER_PROMPT_PATH,
    _validate_llm_classification,
    classify_with_llm,
    generate_profile_with_llm,
    judge_with_llm,
    load_classifier_profile_prompt,
    load_classifier_prompt,
)
from backend.agents.classifier_types import ClassifierProfile
from backend.config import get_settings
from backend.llm.client import LlmClient
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from pydantic import ValidationError

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


def _mock_two_stage_client(
    *,
    profile: ClassifierProfile,
    judge: ParadigmClassification,
    profile_side_effect: Exception | None = None,
) -> LlmClient:
    """Build a mock client where Stage A returns ``profile`` and Stage B returns ``judge``."""

    def _make_runnable(response: object, side_effect: Exception | None = None) -> MagicMock:
        runnable = MagicMock()
        if side_effect is not None:
            runnable.ainvoke = AsyncMock(side_effect=side_effect)
        else:
            runnable.ainvoke = AsyncMock(return_value=response)
        return runnable

    profile_runnable = _make_runnable(profile, profile_side_effect)
    judge_runnable = _make_runnable(judge)

    chat = MagicMock()

    def _with_structured(model: type[object]) -> MagicMock:
        if model is ClassifierProfile:
            return profile_runnable
        if model is ParadigmClassification:
            return judge_runnable
        raise ValueError(f"Unexpected structured output model: {model}")

    chat.with_structured_output.side_effect = _with_structured

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None
    return client


def test_load_classifier_prompt_reads_markdown_file() -> None:
    prompt = load_classifier_prompt()
    assert CLASSIFIER_PROMPT_PATH.is_file()
    assert "STEM" in prompt
    assert "HSS" in prompt
    assert len(prompt.strip()) > 50


def test_classifier_prompt_contains_intent_reranking_red_lines() -> None:
    prompt = load_classifier_prompt().lower()
    assert "hss lock" in prompt
    assert "stem lock" in prompt
    assert "history" in prompt
    assert "archaeology" in prompt
    assert "social phenomenon" in prompt
    assert "cultural anthropology" in prompt
    assert "population evolution" in prompt
    assert "ethnic migration" in prompt
    assert "hard science" in prompt
    assert "mathematics" in prompt
    assert "algorithm itself" in prompt
    assert "engineering artifact" in prompt


def test_load_classifier_profile_prompt_reads_markdown_file() -> None:
    prompt = load_classifier_profile_prompt()
    assert CLASSIFIER_PROFILE_PROMPT_PATH.is_file()
    assert "goal" in prompt.lower()
    assert "tools" in prompt.lower()
    assert "domain" in prompt.lower()
    assert "not" in prompt.lower() and "to classify" in prompt.lower()


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
async def test_generate_profile_with_llm_returns_profile(live_classify_env: None) -> None:
    _ = live_classify_env
    expected = ClassifierProfile(
        goal="Evaluate agents on benchmark datasets.",
        tools="Accuracy, F1, ablation experiments.",
        domain="Computer science / machine learning.",
    )
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=expected)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    result = await generate_profile_with_llm(STEM_SAMPLE, llm_client=client)
    assert result == expected
    chat.with_structured_output.assert_called_once_with(ClassifierProfile)


@pytest.mark.asyncio
async def test_generate_profile_with_llm_rejects_empty_profile(live_classify_env: None) -> None:
    _ = live_classify_env
    bad = ClassifierProfile(goal="   ", tools="x", domain="y")
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=bad)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    with pytest.raises(ValueError, match="Profile goal is empty"):
        await generate_profile_with_llm(STEM_SAMPLE, llm_client=client)


@pytest.mark.asyncio
async def test_classify_with_llm_two_stage_uses_generated_profile(live_classify_env: None) -> None:
    _ = live_classify_env
    profile = ClassifierProfile(
        goal="Benchmark agent frameworks.",
        tools="Datasets, accuracy, F1, ablations.",
        domain="Artificial intelligence / NLP.",
    )
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.92,
        reason="Benchmark and dataset paper.",
    )
    client = _mock_two_stage_client(profile=profile, judge=expected)

    result = await classify_with_llm(STEM_SAMPLE, llm_client=client)

    assert result.paradigm == Paradigm.STEM
    assert client._chat.with_structured_output.call_count == 2
    client._chat.with_structured_output.assert_any_call(ClassifierProfile)
    client._chat.with_structured_output.assert_any_call(ParadigmClassification)


@pytest.mark.asyncio
async def test_classify_with_llm_profile_failure_propagates(live_classify_env: None) -> None:
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.9,
        reason="ok",
    )
    client = _mock_two_stage_client(
        profile=ClassifierProfile(),
        judge=expected,
        profile_side_effect=RuntimeError("profile stage failed"),
    )

    with pytest.raises(RuntimeError, match="profile stage failed"):
        await classify_with_llm(STEM_SAMPLE, llm_client=client)


@pytest.mark.asyncio
async def test_classify_with_llm_single_stage_when_disabled(
    live_classify_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = live_classify_env
    monkeypatch.setenv("CLASSIFIER_TWO_PHASE_ENABLED", "false")
    get_settings.cache_clear()

    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.91,
        reason="Quantitative benchmark paper.",
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
async def test_judge_with_llm_raises_when_both_models_fail(live_classify_env: None) -> None:
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
        await judge_with_llm(STEM_SAMPLE, ClassifierProfile(), llm_client=client)


@pytest.mark.asyncio
async def test_judge_with_llm_primary_success(live_classify_env: None) -> None:
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

    result = await judge_with_llm(STEM_SAMPLE, ClassifierProfile(), llm_client=client)

    assert result.paradigm == Paradigm.STEM
    chat.with_structured_output.assert_called_once_with(ParadigmClassification)


@pytest.mark.asyncio
async def test_judge_with_llm_retries_fallback_model(live_classify_env: None) -> None:
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

    result = await judge_with_llm(
        "Title: Historical ethnography. We analyze archives and interviews.",
        ClassifierProfile(),
        llm_client=client,
    )

    assert result.paradigm == Paradigm.HSS
    primary_chat.with_structured_output.assert_called_once()
    fallback_chat.with_structured_output.assert_called_once()


@pytest.mark.asyncio
async def test_judge_with_llm_recovers_from_markdown_fenced_json(
    live_classify_env: None,
) -> None:
    """If with_structured_output chokes on ```json fences, parse the raw text."""
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.85,
        reason="Experiments and metrics.",
    )
    raw_text = '```json\n{"paradigm": "STEM", "confidence": 0.85, "reason": "Experiments and metrics."}\n```'

    def _raise_fenced(*args: object, **kwargs: object) -> None:
        # Trigger a real Pydantic json_invalid ValidationError.
        ParadigmClassification.model_validate_json(raw_text)

    primary_runnable = MagicMock()
    primary_runnable.ainvoke = AsyncMock(side_effect=_raise_fenced)
    fallback_runnable = MagicMock()
    fallback_runnable.ainvoke = AsyncMock(return_value=expected)

    primary_chat = MagicMock()
    primary_chat.with_structured_output.return_value = primary_runnable
    fallback_chat = MagicMock()
    fallback_chat.with_structured_output.return_value = fallback_runnable

    client = LlmClient()
    client._chat = primary_chat
    client._fallback_chat = fallback_chat

    result = await judge_with_llm(STEM_SAMPLE, ClassifierProfile(), llm_client=client)
    assert result.paradigm == Paradigm.STEM
    assert result.confidence == 0.85


@pytest.mark.parametrize(
    "raw_output",
    [
        '{"paradigm": "STEM", "confidence": 0.9, "reason": "Plain JSON."}',
        '```json\n{"paradigm": "STEM", "confidence": 0.9, "reason": "Fenced JSON."}\n```',
        'Some preamble text {"paradigm": "STEM", "confidence": 0.9, "reason": "Embedded JSON."} trailing text',
        '{"paradigm": "STEM", "confidence": 0.9, "reason": "Trailing comma",}',
        '  \n  {"paradigm": "STEM", "confidence": 0.9, "reason": "Whitespace surrounded."}  \n  ',
    ],
    ids=["plain", "fenced", "embedded", "trailing_comma", "whitespace"],
)
@pytest.mark.asyncio
async def test_judge_with_llm_parses_various_string_outputs(
    live_classify_env: None,
    raw_output: str,
) -> None:
    """Robust data cleaning tolerates common LLM JSON formatting mistakes."""
    _ = live_classify_env
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=raw_output)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    result = await judge_with_llm(STEM_SAMPLE, ClassifierProfile(), llm_client=client)
    assert result.paradigm == Paradigm.STEM
    assert result.confidence == 0.9


@pytest.mark.parametrize(
    "raw_output",
    [
        '{"confidence": 0.9, "reason": "Missing paradigm."}',
        '{"paradigm": "INVALID", "confidence": 0.9, "reason": "Bad paradigm."}',
        "not json at all",
    ],
    ids=["missing_paradigm", "invalid_paradigm", "non_json"],
)
@pytest.mark.asyncio
async def test_judge_with_llm_rejects_invalid_outputs(
    live_classify_env: None,
    raw_output: str,
) -> None:
    """Invalid string outputs must still fail and trigger fallback logic upstream."""
    _ = live_classify_env
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=raw_output)
    chat = MagicMock()
    chat.with_structured_output.return_value = structured_runnable

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    with pytest.raises((ValidationError, ValueError)):
        await judge_with_llm(STEM_SAMPLE, ClassifierProfile(), llm_client=client)


@pytest.mark.asyncio
async def test_classify_two_stage_profile_failure_falls_back_to_heuristic(live_classify_env: None) -> None:
    """If Stage A profile generation fails, classify() degrades to heuristic."""
    from unittest.mock import patch

    _ = live_classify_env
    with patch(
        "backend.agents.classifier_llm.generate_profile_with_llm",
        new=AsyncMock(side_effect=RuntimeError("profile stage failed")),
    ):
        result = await classify(STEM_SAMPLE)

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.classification.paradigm == Paradigm.STEM
