# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tenacity retry policy for cloud Reranker calls (429 / 5xx / network resilience)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# Default aligned with Settings.reranker_max_retries / RERANKER_MAX_RETRIES.
RERANK_RETRY_ATTEMPTS = 3
RERANK_RETRY_WAIT = wait_exponential(multiplier=1, min=2, max=30)

_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_TRANSIENT_MARKERS = (
    "rate limit",
    "429",
    "too many requests",
    "modelarts.81101",
    "timeout",
    "timed out",
    "connection reset",
    "connection error",
    "connect timeout",
    "503",
    "502",
    "504",
    "overloaded",
    "temporarily unavailable",
)

T = TypeVar("T")


def is_transient_rerank_error(exc: BaseException) -> bool:
    """Return True when the error is likely transient (rate limit / network / 5xx)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _TRANSIENT_STATUS_CODES
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def _attempt_limit() -> int:
    try:
        from backend.config import get_settings

        return max(1, get_settings().reranker_max_retries)
    except Exception:
        return RERANK_RETRY_ATTEMPTS


async def run_with_rerank_retry(operation: Callable[[], Awaitable[T]]) -> T:
    """Execute an async Reranker operation with exponential backoff on transient errors.

    Mirrors ``run_with_judge_retry`` (same wait / before_sleep / reraise semantics) but
    uses ``AsyncRetrying`` so ``RERANKER_MAX_RETRIES`` is honored at call time.
    """
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(_attempt_limit()),
        wait=RERANK_RETRY_WAIT,
        retry=retry_if_exception(is_transient_rerank_error),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    ):
        with attempt:
            return await operation()
    msg = "rerank retry exhausted without result"
    raise RuntimeError(msg)
