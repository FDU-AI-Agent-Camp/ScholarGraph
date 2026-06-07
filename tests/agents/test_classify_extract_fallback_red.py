"""
红灯：分类成功但抽取 fallback 的边界与根因可观测性。

运行：uv run pytest -m red tests/agents/test_classify_extract_fallback_red.py -rx
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.agents.extractor import extract
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm, ParadigmClassification

pytestmark = pytest.mark.red

STEM_INPUT = "Title: Crystal GNN benchmark. Datasets, accuracy, baselines, neural networks, experiments."


@pytest.fixture
def live_both_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


@pytest.mark.asyncio
async def test_red_classify_clean_extract_fallback_api_codes_differ(live_both_llm_env: None) -> None:
    """API 机器码：classify 无 fallback 码，extract 有 extract_heuristic_fallback。"""
    _ = live_both_llm_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.9,
        reason="STEM metrics paper.",
    )
    with patch(
        "backend.agents.classifier.classify_with_llm",
        new=AsyncMock(return_value=expected),
    ):
        classify_result = await classify(STEM_INPUT)

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=ValueError("LLM graph has no edges.")),
    ):
        extract_result = await extract(STEM_INPUT, Paradigm.STEM, paper_id="red-split")

    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE not in classify_result.warnings
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in extract_result.warnings


@pytest.mark.asyncio
async def test_red_extract_fallback_reason_not_in_api_warnings(live_both_llm_env: None) -> None:
    """根因仅在日志 reason；status/API warnings 不含异常文本。"""
    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_MESSAGE

    _ = live_both_llm_env
    secret_reason = "LLM graph has no nodes."

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=ValueError(secret_reason)),
    ):
        result = await extract(STEM_INPUT, Paradigm.STEM, paper_id="red-no-leak")

    assert result.warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]
    assert secret_reason not in result.warnings
    assert EXTRACT_HEURISTIC_FALLBACK_MESSAGE not in result.warnings


@pytest.mark.asyncio
async def test_red_classifier_and_extract_use_separate_env_flags(
    live_both_llm_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLASSIFIER_LLM_ENABLED 与 EXTRACT_LLM_ENABLED 可独立关闭。"""
    _ = live_both_llm_env
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as classify_llm:
        classify_result = await classify(STEM_INPUT)

    classify_llm.assert_not_awaited()
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE in classify_result.warnings

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("extract failed")),
    ):
        extract_result = await extract(STEM_INPUT, Paradigm.STEM, paper_id="red-flags")

    assert EXTRACT_HEURISTIC_FALLBACK_CODE in extract_result.warnings
