"""G2.9: classify_llm_fallback / classify_llm_disabled logs include reason."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.mark.asyncio
async def test_g29_classify_llm_fallback_log_includes_reason(
    live_classify_env: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ = live_classify_env
    caplog.set_level("WARNING", logger="backend.agents.classifier")

    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(side_effect=RuntimeError("structured output failed")),
    ):
        await classify(STEM_SAMPLE)

    records = [record for record in caplog.records if record.getMessage() == "classify_llm_fallback"]
    assert len(records) == 1
    assert "structured output failed" in str(getattr(records[0], "reason", ""))


@pytest.mark.asyncio
async def test_g29_classify_llm_disabled_log_includes_reason(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()
    caplog.set_level("WARNING", logger="backend.agents.classifier")

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    records = [record for record in caplog.records if record.getMessage() == "classify_llm_disabled"]
    assert len(records) == 1
    assert getattr(records[0], "reason", None) == "classifier_llm_disabled"
