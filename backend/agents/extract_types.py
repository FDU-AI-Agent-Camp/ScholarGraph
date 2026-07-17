# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Types for graph extraction results and errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NoReturn

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
        APIStatusError = APITimeoutError = BadRequestError = NotFoundError = RateLimitError = None  # type: ignore

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

    openai_errors: tuple[Any, ...] = (
        APITimeoutError,
        RateLimitError,
        BadRequestError,
        NotFoundError,
        APIStatusError,
    )
    openai_errors = tuple(e for e in openai_errors if e is not None)
    if openai_errors and isinstance(exc, openai_errors):
        if isinstance(exc, (APITimeoutError, RateLimitError)):  # type: ignore
            raise TransientExtractionError(f"OpenAI timeout/rate limit: {exc}") from exc
        if isinstance(exc, (BadRequestError, NotFoundError)):  # type: ignore
            raise DeterministicExtractionError(f"OpenAI client error: {exc}") from exc
        if isinstance(exc, APIStatusError):  # type: ignore
            status_code = getattr(exc, "status_code", 0)
            if status_code in {429, 502, 503, 504}:
                raise TransientExtractionError(f"OpenAI status {status_code}: {exc}") from exc
            if status_code >= 400:
                raise DeterministicExtractionError(f"OpenAI client error {status_code}: {exc}") from exc

    # Deterministic: validation failures, JSON parse errors, context too long, unknown errors
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        if "validation" in msg or "forbidden" in msg or "schema" in msg:
            raise DeterministicExtractionError(f"Schema validation failed: {exc}") from exc
        # Typically JSON parse failures from malformed LLM output
        raise DeterministicExtractionError(f"LLM output parse error: {exc}") from exc

    # Unknown exceptions are treated as deterministic. Retrying an unknown error
    # is usually wasteful; callers should fallback or surface it directly.
    raise DeterministicExtractionError(f"Unexpected extraction error: {type(exc).__name__}: {exc}") from exc
