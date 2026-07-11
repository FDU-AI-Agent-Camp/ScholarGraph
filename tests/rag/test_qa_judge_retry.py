"""Tests for Judge LLM tenacity retry and transient error classification."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.rag.models import QAJudgeResult
from backend.rag.qa_judge import invoke_qa_judge
from backend.rag.qa_judge_retry import is_transient_judge_error, run_with_judge_retry


def test_is_transient_judge_error_detects_rate_limit_and_timeout() -> None:
    assert is_transient_judge_error(TimeoutError("timed out")) is True
    assert is_transient_judge_error(RuntimeError("HTTP 429 rate limit exceeded")) is True
    assert is_transient_judge_error(ValueError("invalid json schema")) is False


@pytest.mark.asyncio
async def test_run_with_judge_retry_recovers_after_transient_failures() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("429 rate limit exceeded")
        return "ok"

    result = await run_with_judge_retry(flaky)
    assert result == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_run_with_judge_retry_does_not_retry_deterministic_errors() -> None:
    attempts = 0

    async def broken() -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("schema validation failed")

    with pytest.raises(ValueError, match="schema validation failed"):
        await run_with_judge_retry(broken)
    assert attempts == 1


@pytest.mark.asyncio
async def test_invoke_qa_judge_live_path_uses_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.llm.client import LlmClient, reset_llm_client_cache
    from backend.config import get_settings

    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    attempts = 0

    async def _flaky_structured(_client: object, _messages: object, **_kwargs: object) -> QAJudgeResult:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("503 temporarily unavailable")
        return QAJudgeResult(
            factual_consistency=1.0,
            hallucination_detected=False,
            reasoning="recovered",
        )

    client = LlmClient()
    with patch("backend.rag.qa_judge.invoke_judge_structured_output", side_effect=_flaky_structured):
        result = await invoke_qa_judge(
            client,
            question="q",
            paradigm="STEM",
            answer_text="answer",
            citations=[],
            gold={"required_patterns": [], "forbidden_patterns": [], "nodes": [], "edges": []},
        )

    assert result.reasoning == "recovered"
    assert attempts == 2
