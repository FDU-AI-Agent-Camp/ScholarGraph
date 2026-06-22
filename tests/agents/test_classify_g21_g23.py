"""Phase G.2 acceptance: classify_with_llm primary path (G2.1–G2.3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.classifier_llm import classify_with_llm, judge_with_llm
from backend.agents.classifier_types import ClassifierProfile
from backend.llm.client import LlmClient
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from pydantic import ValidationError

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


def _make_runnable(response: object) -> MagicMock:
    runnable = MagicMock()
    runnable.ainvoke = AsyncMock(return_value=response)
    return runnable


def _mock_client_for_judge(
    *,
    primary_response: object,
    fallback_response: object | None = None,
) -> LlmClient:
    primary_runnable = _make_runnable(primary_response)
    primary_chat = MagicMock()
    primary_chat.with_structured_output.return_value = primary_runnable

    client = LlmClient()
    client._chat = primary_chat
    if fallback_response is None:
        client._fallback_chat = None
    else:
        fallback_runnable = _make_runnable(fallback_response)
        fallback_chat = MagicMock()
        fallback_chat.with_structured_output.return_value = fallback_runnable
        client._fallback_chat = fallback_chat
    return client


# ── G2.1: structured LLM → ParadigmClassification ───────────────────────────


def test_g21_pydantic_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ParadigmClassification(paradigm=Paradigm.STEM, confidence=1.5, reason="ok")


def test_g21_pydantic_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.5, reason="")


def test_g21_pydantic_accepts_valid_stem_and_hss() -> None:
    stem = ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.0, reason="x")
    hss = ParadigmClassification(paradigm=Paradigm.HSS, confidence=1.0, reason="y")
    assert stem.paradigm == Paradigm.STEM
    assert hss.paradigm == Paradigm.HSS


@pytest.mark.asyncio
async def test_g21_classify_with_llm_returns_paradigm_classification(live_classify_env: None) -> None:
    """Mock LlmClient.with_structured_output → valid ParadigmClassification."""
    _ = live_classify_env
    profile = ClassifierProfile(
        goal="Benchmark agents.",
        tools="Datasets, metrics.",
        domain="AI/ML.",
    )
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.93,
        reason="Quantitative benchmark with datasets and metrics.",
    )

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

    assert isinstance(result, ParadigmClassification)
    assert result.paradigm == Paradigm.STEM
    assert 0.0 <= result.confidence <= 1.0
    assert result.reason.strip()
    chat.with_structured_output.assert_any_call(ClassifierProfile)
    chat.with_structured_output.assert_any_call(ParadigmClassification)


@pytest.mark.asyncio
async def test_g21_judge_with_llm_model_validates_dict_payload(live_classify_env: None) -> None:
    """LLM may return a plain dict; _invoke_structured coerces via Pydantic."""
    _ = live_classify_env
    payload = {
        "paradigm": "HSS",
        "confidence": 0.77,
        "reason": "Qualitative theory-driven study.",
    }
    chat = MagicMock()
    chat.with_structured_output.return_value = _make_runnable(payload)
    client = LlmClient()
    client._chat = chat
    client._fallback_chat = None

    result = await judge_with_llm(
        STEM_SAMPLE,
        ClassifierProfile(),
        llm_client=client,
    )

    assert isinstance(result, ParadigmClassification)
    assert result.paradigm == Paradigm.HSS
    assert result.confidence == 0.77


# ── G2.2: primary failure → fallback model success ──────────────────────────


@pytest.mark.asyncio
async def test_g22_primary_failure_retries_fallback_model(live_classify_env: None) -> None:
    expected = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.86,
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
    primary_runnable.ainvoke.assert_awaited_once()
    fallback_runnable.ainvoke.assert_awaited_once()


# ── G2.3: LLM total failure → heuristic + warnings; classify_node persists ──


@pytest.mark.asyncio
async def test_g23_llm_total_failure_yields_heuristic_and_warning(live_classify_env: None) -> None:
    from unittest.mock import patch

    _ = live_classify_env
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        result = await classify(STEM_SAMPLE)

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in result.warnings
    assert result.classification.paradigm == Paradigm.STEM
