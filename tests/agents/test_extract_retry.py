"""Tests for extraction retry / fallback exception taxonomy."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from backend.agents.extract_constants import (
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    EXTRACT_LLM_JSON_INVALID_CODE,
    EXTRACT_LLM_RATE_LIMITED_CODE,
    EXTRACT_LLM_TIMEOUT_CODE,
    EXTRACT_SCHEMA_VALIDATION_FAILED_CODE,
)
from backend.agents.extract_retry import warning_code_for_error as _warning_code_for_error
from backend.agents.extract_types import (
    DeterministicExtractionError,
    TransientExtractionError,
    classify_extraction_error,
)
from backend.config import Settings
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


def test_classify_timeout_as_transient() -> None:
    original = httpx.TimeoutException("request timed out")
    with pytest.raises(TransientExtractionError):
        classify_extraction_error(original)


def test_classify_rate_limit_http_status_as_transient() -> None:
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    original = httpx.HTTPStatusError("rate limited", request=request, response=response)
    with pytest.raises(TransientExtractionError):
        classify_extraction_error(original)


def test_classify_bad_request_http_status_as_deterministic() -> None:
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(400, request=request)
    original = httpx.HTTPStatusError("bad request", request=request, response=response)
    with pytest.raises(DeterministicExtractionError):
        classify_extraction_error(original)


def test_classify_value_error_as_deterministic() -> None:
    original = ValueError("Model returned non-JSON content")
    with pytest.raises(DeterministicExtractionError):
        classify_extraction_error(original)


def test_classify_unknown_error_as_deterministic() -> None:
    original = RuntimeError("something unexpected")
    with pytest.raises(DeterministicExtractionError):
        classify_extraction_error(original)


def test_warning_code_for_rate_limit() -> None:
    exc = TransientExtractionError("OpenAI rate limit: 429")
    assert _warning_code_for_error(exc) == EXTRACT_LLM_RATE_LIMITED_CODE


def test_warning_code_for_timeout() -> None:
    exc = TransientExtractionError("LLM request timed out")
    assert _warning_code_for_error(exc) == EXTRACT_LLM_TIMEOUT_CODE


def test_warning_code_for_json_invalid() -> None:
    exc = DeterministicExtractionError("LLM output parse error")
    assert _warning_code_for_error(exc) == EXTRACT_LLM_JSON_INVALID_CODE


def test_warning_code_for_validation() -> None:
    exc = DeterministicExtractionError("Schema validation failed")
    assert _warning_code_for_error(exc) == EXTRACT_SCHEMA_VALIDATION_FAILED_CODE


def test_warning_code_fallback_for_unmapped() -> None:
    exc = DeterministicExtractionError("some other deterministic failure")
    assert _warning_code_for_error(exc) == EXTRACT_HEURISTIC_FALLBACK_CODE


@pytest.mark.asyncio
async def test_handle_failure_runs_fallback_for_deterministic_error() -> None:
    """Deterministic errors should trigger the fallback action immediately."""
    from backend.agents.extractor import _handle_extract_failure

    settings = Settings(_env_file=None, extract_heuristic_fallback=True)
    fallback_action = Mock()
    fallback_action.return_value.warnings = [EXTRACT_HEURISTIC_FALLBACK_CODE]

    result = _handle_extract_failure(
        DeterministicExtractionError("deterministic failure"),
        settings=settings,
        paper_id="paper-001",
        fallback_action=fallback_action,
    )
    fallback_action.assert_called_once()
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings


@pytest.mark.asyncio
async def test_handle_failure_falls_back_for_transient_error() -> None:
    """After tenacity exhausts retries, transient errors also degrade to fallback."""
    from backend.agents.extractor import _handle_extract_failure

    settings = Settings(_env_file=None, extract_heuristic_fallback=True)
    fallback_action = Mock()
    fallback_action.return_value.warnings = [EXTRACT_LLM_TIMEOUT_CODE, EXTRACT_HEURISTIC_FALLBACK_CODE]

    result = _handle_extract_failure(
        TransientExtractionError("transient failure"),
        settings=settings,
        paper_id="paper-001",
        fallback_action=fallback_action,
    )
    fallback_action.assert_called_once()
    assert EXTRACT_LLM_TIMEOUT_CODE in result.warnings
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings


@pytest.mark.asyncio
async def test_extract_single_phase_retries_transient_errors_then_succeeds() -> None:
    """Transient errors should be retried by tenacity before returning the graph."""
    from backend.agents.extractor import _extract_single_phase

    settings = Settings(_env_file=None)
    llm_mock = AsyncMock(
        side_effect=[
            TransientExtractionError("timeout"),
            TransientExtractionError("timeout"),
            UnifiedPaperGraph(
                paper_id="p",
                paradigm=Paradigm.HSS,
                nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
                edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
            ),
        ],
    )

    with patch("backend.agents.extractor.extract_with_llm", new=llm_mock):
        result = await _extract_single_phase(
            "text",
            Paradigm.HSS,
            paper_id="p",
            title="t",
            head_context=None,
            settings=settings,
        )

    assert llm_mock.await_count == 3
    assert result.graph.paper_id == "p"



