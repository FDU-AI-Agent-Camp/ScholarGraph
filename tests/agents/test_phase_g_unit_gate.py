"""Phase G acceptance gate: LLM success and heuristic fallback unit paths."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.classifier_llm import classify_with_llm
from backend.agents.classifier_types import ClassifierProfile, ClassifyResult
from backend.config import get_settings
from backend.llm.client import LlmClient, reset_llm_client_cache
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.mark.asyncio
async def test_g7_classify_with_llm_structured_success(live_classify_env: None) -> None:
    """G7: mock with_structured_output → valid classification."""
    _ = live_classify_env
    profile = ClassifierProfile(
        goal="Benchmark agent frameworks.",
        tools="Datasets, accuracy, F1, ablations.",
        domain="Artificial intelligence.",
    )
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.91,
        reason="Quantitative benchmark paper.",
    )

    def _make_runnable(response: object) -> MagicMock:
        runnable = MagicMock()
        runnable.ainvoke = AsyncMock(return_value=response)
        return runnable

    chat = MagicMock()

    def _with_structured(model: type[object]) -> MagicMock:
        if model is ClassifierProfile:
            return _make_runnable(profile)
        if model is ParadigmClassification:
            return _make_runnable(expected)
        raise ValueError(f"Unexpected model: {model}")

    chat.with_structured_output.side_effect = _with_structured

    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    result = await classify_with_llm(STEM_SAMPLE, llm_client=client)
    assert result.paradigm == Paradigm.STEM
    chat.with_structured_output.assert_any_call(ClassifierProfile)
    chat.with_structured_output.assert_any_call(ParadigmClassification)

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(return_value=expected),
    ):
        wrapped = await classify(STEM_SAMPLE)

    assert isinstance(wrapped, ClassifyResult)
    assert wrapped.warnings == []
    assert wrapped.classification.paradigm == Paradigm.STEM


@pytest.mark.asyncio
async def test_g8_llm_failure_falls_back_with_classifier_heuristic_fallback_code(
    live_classify_env: None,
) -> None:
    """G8: LLM error → heuristic classification + classifier_heuristic_fallback."""
    _ = live_classify_env

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await classify(STEM_SAMPLE)

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.classification.paradigm == Paradigm.STEM


@pytest.mark.asyncio
async def test_g8_no_fallback_raises_service_error(
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
async def test_g24_llm_disabled_symmetric_with_extract_disabled_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G2.4: live + CLASSIFIER_LLM_ENABLED=false → heuristic + warning (mirror extract disabled)."""
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


def test_g_frozen_warning_code_emitted_by_fallback_helper() -> None:
    from backend.agents import classifier

    source = inspect.getsource(classifier._fallback_to_heuristic)
    assert "CLASSIFIER_HEURISTIC_FALLBACK_CODE" in source
    assert "CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE" not in source
