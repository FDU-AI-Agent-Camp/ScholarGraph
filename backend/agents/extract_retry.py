"""Retry, failure classification and fallback helpers for graph extraction.

This module is intentionally separated from ``backend.agents.extractor`` to keep
the orchestrator module small (DoD D-12 line budget) while still keeping the
retry policy, exception taxonomy and warning-code mapping in one place.
"""

from __future__ import annotations

from collections.abc import Callable

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.agents.extract_constants import (
    EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE,
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    EXTRACT_LLM_JSON_INVALID_CODE,
    EXTRACT_LLM_RATE_LIMITED_CODE,
    EXTRACT_LLM_TIMEOUT_CODE,
    EXTRACT_SCHEMA_VALIDATION_FAILED_CODE,
)
from backend.agents.extract_types import (
    DeterministicExtractionError,
    ExtractResult,
    TransientExtractionError,
    classify_extraction_error,
)
from backend.config import Settings
from backend.schemas.extract_phase import ExtractedGraph
from backend.schemas.paradigm import Paradigm
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError

# Retry transient extraction failures with exponential backoff.
_RETRY_CONFIG = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=2, max=30),
    "retry": retry_if_exception_type(TransientExtractionError),
    "reraise": True,
}


def warning_code_for_error(exc: BaseException | str) -> str:
    """Map an extraction failure to a fine-grained machine-readable warning code."""
    msg = str(exc).lower()
    if "rate limit" in msg or "429" in msg:
        return EXTRACT_LLM_RATE_LIMITED_CODE
    if "timeout" in msg or "timed out" in msg:
        return EXTRACT_LLM_TIMEOUT_CODE
    if "context window" in msg or "context length" in msg or "token" in msg:
        return EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE
    if "validation" in msg or "schema" in msg:
        return EXTRACT_SCHEMA_VALIDATION_FAILED_CODE
    if "json" in msg or "parse" in msg:
        return EXTRACT_LLM_JSON_INVALID_CODE
    return EXTRACT_HEURISTIC_FALLBACK_CODE


def handle_extract_failure(
    exc: BaseException,
    *,
    settings: Settings,
    paper_id: str,
    fallback_action: Callable[[BaseException], ExtractResult],
) -> ExtractResult:
    """Classify an extraction failure and degrade to heuristic fallback.

    By the time this helper is called the retry layer (tenacity) has already
    exhausted its attempts for transient errors. All failures therefore land
    here as final errors and should be mapped to a fallback warning unless
    heuristic fallback is disabled.
    """
    try:
        classify_extraction_error(exc)
    except (TransientExtractionError, DeterministicExtractionError) as classified:
        if not settings.extract_heuristic_fallback:
            raise ServiceError(PIPELINE_FAILED_CODE, f"图谱 LLM 抽取失败: {classified}") from classified
        return fallback_action(classified)

    # Unreachable: classify_extraction_error always raises an ExtractionError.
    raise ServiceError(PIPELINE_FAILED_CODE, f"图谱 LLM 抽取失败: {exc}") from exc


@retry(**_RETRY_CONFIG)
async def extract_chunked_with_retry(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str,
    head_context: str | None,
    settings: Settings,
) -> ExtractedGraph:
    """Chunked two-phase extraction with tenacity retry on transient failures."""
    from backend.agents.extract_chunked import extract_chunked

    return await extract_chunked(
        full_text,
        paradigm,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
        settings=settings,
    )


@retry(**_RETRY_CONFIG)
async def run_extract_subgraph_with_retry(
    full_text: str,
    paradigm: Paradigm,
    *,
    paper_id: str,
    title: str,
    head_context: str | None,
) -> ExtractResult:
    """LangGraph two-phase sub-graph with tenacity retry on transient failures."""
    from backend.graph.extract_workflow import run_extract_subgraph

    return await run_extract_subgraph(
        full_text,
        paradigm,
        paper_id=paper_id,
        title=title,
        head_context=head_context,
    )
