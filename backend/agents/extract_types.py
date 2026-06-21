"""Types for graph extraction results and errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NoReturn

from backend.schemas.graph import UnifiedPaperGraph


@dataclass(frozen=True)
class ExtractResult:
    """Graph extraction output plus optional degrade warnings."""

    graph: UnifiedPaperGraph
    warnings: list[str] = field(default_factory=list)


class ExtractionError(Exception):
    """Base class for extraction-stage failures."""


class TransientExtractionError(ExtractionError):
    """A failure that may resolve by retrying (timeout, rate limit, network).

    The retry layer (tenacity) will catch this and apply exponential backoff.
    """


class DeterministicExtractionError(ExtractionError):
    """A failure that is unlikely to resolve by retrying (schema, bad request).

    Callers should degrade to heuristic fallback rather than retrying forever.
    """


def classify_extraction_error(exc: BaseException) -> NoReturn:
    """Classify an arbitrary exception into transient or deterministic.

    This centralizes the taxonomy so the retry layer and fallback layer agree
    on which failures are worth retrying. The function always raises an
    ``ExtractionError`` subclass rather than returning it.
    """
    import httpx

    try:
        from openai import (
            APIStatusError,
            APITimeoutError,
            BadRequestError,
            NotFoundError,
            RateLimitError,
        )
    except Exception:  # pragma: no cover - openai may not be installed in all tests
        APIStatusError = APITimeoutError = BadRequestError = NotFoundError = RateLimitError = None  # type: ignore[misc, assignment]

    # Transient: network / timeout / rate limit / server errors
    if isinstance(exc, httpx.TimeoutException):
        raise TransientExtractionError(f"LLM request timed out: {exc}") from exc
    if isinstance(exc, httpx.NetworkError):
        raise TransientExtractionError(f"LLM network error: {exc}") from exc
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if hasattr(exc, "response") else 0
        if status_code in {429, 502, 503, 504}:
            raise TransientExtractionError(f"LLM upstream error {status_code}: {exc}") from exc
        if status_code >= 400:
            raise DeterministicExtractionError(f"LLM client error {status_code}: {exc}") from exc

    if APIStatusError is not None:
        if isinstance(exc, APITimeoutError):
            raise TransientExtractionError(f"OpenAI timeout: {exc}") from exc
        if isinstance(exc, RateLimitError):
            raise TransientExtractionError(f"OpenAI rate limit: {exc}") from exc
        if isinstance(exc, (BadRequestError, NotFoundError)):
            raise DeterministicExtractionError(f"OpenAI client error: {exc}") from exc
        if isinstance(exc, APIStatusError):
            status_code = getattr(exc, "status_code", 0)
            if status_code in {429, 502, 503, 504}:
                raise TransientExtractionError(f"OpenAI status {status_code}: {exc}") from exc
            if status_code >= 400:
                raise DeterministicExtractionError(f"OpenAI client error {status_code}: {exc}") from exc

    # Deterministic: validation failures, JSON parse errors, context too long, unknown errors
    if isinstance(exc, ValueError):
        # Typically JSON parse failures from malformed LLM output
        raise DeterministicExtractionError(f"LLM output parse error: {exc}") from exc

    # Unknown exceptions are treated as deterministic. Retrying an unknown error
    # is usually wasteful; callers should fallback or surface it directly.
    raise DeterministicExtractionError(f"Unexpected extraction error: {type(exc).__name__}: {exc}") from exc
