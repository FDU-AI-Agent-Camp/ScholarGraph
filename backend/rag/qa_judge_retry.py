"""Tenacity retry policy for live Judge LLM calls (TPM/RPM rate-limit resilience)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

JUDGE_RETRY_ATTEMPTS = 3
JUDGE_RETRY_WAIT = wait_exponential(multiplier=1, min=2, max=30)

_TRANSIENT_MARKERS = (
    "rate limit",
    "429",
    "too many requests",
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


def is_transient_judge_error(exc: BaseException) -> bool:
    """Return True when the error is likely transient (rate limit / network / 5xx)."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


@retry(
    stop=stop_after_attempt(JUDGE_RETRY_ATTEMPTS),
    wait=JUDGE_RETRY_WAIT,
    retry=retry_if_exception(is_transient_judge_error),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def run_with_judge_retry(operation: Callable[[], Awaitable[T]]) -> T:
    """Execute an async Judge operation with exponential backoff on transient errors."""
    return await operation()
