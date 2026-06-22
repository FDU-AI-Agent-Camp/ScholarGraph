"""Red-light / boundary tests for extraction retry and fallback taxonomy."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from backend.agents.extract_constants import (
    EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE,
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    EXTRACT_LLM_JSON_INVALID_CODE,
    EXTRACT_LLM_RATE_LIMITED_CODE,
    EXTRACT_LLM_TIMEOUT_CODE,
    EXTRACT_SCHEMA_VALIDATION_FAILED_CODE,
)
from backend.agents.extract_types import TransientExtractionError
from backend.config import Settings
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.errors import ServiceError

pytestmark = [pytest.mark.red]


@pytest.fixture
def live_extract_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings that enable LLM + fallback for red tests (network is mocked)."""
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "red-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")
    monkeypatch.setenv("EXTRACT_TWO_PHASE_ENABLED", "false")
    from backend.config import get_settings
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()
    return Settings(_env_file=None)


@pytest.mark.asyncio
async def test_red_deterministic_error_falls_back_without_retry(live_extract_settings: Settings) -> None:
    """Deterministic failures must not waste retry budget."""
    from backend.agents.extractor import extract

    llm_mock = AsyncMock(side_effect=ValueError("LLM graph has no nodes."))

    with patch("backend.agents.extractor.extract_with_llm", new=llm_mock):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-det")

    assert llm_mock.await_count == 1
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert EXTRACT_LLM_JSON_INVALID_CODE in result.warnings


@pytest.mark.asyncio
async def test_red_transient_error_retries_then_falls_back(live_extract_settings: Settings) -> None:
    """Transient failures must consume the full tenacity retry budget before fallback."""
    from backend.agents.extractor import extract

    llm_mock = AsyncMock(side_effect=TransientExtractionError("timeout"))

    with patch("backend.agents.extractor.extract_with_llm", new=llm_mock):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-trans")

    assert llm_mock.await_count == 3
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in result.warnings
    assert EXTRACT_LLM_TIMEOUT_CODE in result.warnings


@pytest.mark.asyncio
async def test_red_transient_retries_then_succeeds(live_extract_settings: Settings) -> None:
    """If the transient error resolves within the retry budget, no fallback occurs."""
    from backend.agents.extractor import extract

    success_graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    llm_mock = AsyncMock(
        side_effect=[
            TransientExtractionError("timeout"),
            TransientExtractionError("timeout"),
            success_graph,
        ],
    )

    with patch("backend.agents.extractor.extract_with_llm", new=llm_mock):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-trans-ok")

    assert llm_mock.await_count == 3
    assert result.warnings == []
    assert result.graph.paper_id == "red-trans-ok"


@pytest.mark.asyncio
async def test_red_fallback_disabled_raises_service_error(
    live_extract_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With EXTRACT_HEURISTIC_FALLBACK=false any final failure becomes a hard error."""
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "false")
    from backend.config import get_settings
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()

    from backend.agents.extractor import extract

    with (
        patch("backend.agents.extractor.extract_with_llm", new=AsyncMock(side_effect=RuntimeError("boom"))),
        pytest.raises(ServiceError, match="图谱 LLM 抽取失败"),
    ):
        await extract("标题：测试", Paradigm.HSS, paper_id="red-no-fallback")


@pytest.mark.asyncio
async def test_red_timeout_error_maps_to_timeout_warning(live_extract_settings: Settings) -> None:
    from backend.agents.extractor import extract

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock(side_effect=TimeoutError("api timeout"))):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-timeout")

    assert EXTRACT_LLM_TIMEOUT_CODE in result.warnings


@pytest.mark.asyncio
async def test_red_rate_limit_error_maps_to_rate_limited_warning(live_extract_settings: Settings) -> None:
    from backend.agents.extractor import extract

    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)

    with patch("backend.agents.extractor.extract_with_llm", new=AsyncMock(side_effect=exc)):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-rate")

    assert EXTRACT_LLM_RATE_LIMITED_CODE in result.warnings


@pytest.mark.asyncio
async def test_red_schema_validation_error_maps_to_schema_warning(live_extract_settings: Settings) -> None:
    from backend.agents.extractor import extract

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=ValueError("HSS graph contains forbidden node types: ['Metric']")),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-schema")

    assert EXTRACT_SCHEMA_VALIDATION_FAILED_CODE in result.warnings


@pytest.mark.asyncio
async def test_red_context_window_error_maps_to_context_warning(live_extract_settings: Settings) -> None:
    from backend.agents.extractor import extract

    with patch(
        "backend.agents.extractor.extract_with_llm",
        new=AsyncMock(side_effect=RuntimeError("context window exceeded")),
    ):
        result = await extract("标题：测试", Paradigm.HSS, paper_id="red-ctx")

    assert EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE in result.warnings


def test_red_handle_failure_fallback_disabled_for_transient() -> None:
    """Even transient errors become hard failures when fallback is disabled."""
    from backend.agents.extractor import _handle_extract_failure

    settings = Settings(_env_file=None, extract_heuristic_fallback=False)
    fallback_action = Mock()

    with pytest.raises(ServiceError):
        _handle_extract_failure(
            TransientExtractionError("timeout"),
            settings=settings,
            paper_id="red-handle-trans",
            fallback_action=fallback_action,
        )
    fallback_action.assert_not_called()
