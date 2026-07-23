# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Async token-bucket rate limiter for LLM calls (Slice 2).

Enforces both requests-per-minute (RPM) and tokens-per-minute (TPM) caps using
a sliding token bucket.  The limiter is shared per-process; callers await
``acquire(tokens=1, chars=N)`` before each LLM request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import lru_cache

logger = logging.getLogger(__name__)


class AsyncTokenBucket:
    """Token bucket that throttles on both request count and token/character budget.

    Args:
        rpm: Maximum requests per minute.  ``0`` disables request-rate limiting.
        tpm: Maximum tokens (or characters, if no tokenizer is available) per minute.
            ``0`` disables token-rate limiting.
    """

    def __init__(self, rpm: int, tpm: int) -> None:
        self._rpm = max(rpm, 0)
        self._tpm = max(tpm, 0)
        self._request_tokens = float(self._rpm)
        self._token_tokens = float(self._tpm)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def rpm(self) -> int:
        return self._rpm

    @property
    def tpm(self) -> int:
        return self._tpm

    def _replenish(self, now: float) -> None:
        elapsed = now - self._last_update
        if self._rpm > 0:
            self._request_tokens = min(self._rpm, self._request_tokens + elapsed * (self._rpm / 60.0))
        if self._tpm > 0:
            self._token_tokens = min(self._tpm, self._token_tokens + elapsed * (self._tpm / 60.0))
        self._last_update = now

    async def acquire(self, *, tokens: int = 1, chars: int = 0) -> None:
        """Wait until ``tokens`` requests and ``chars`` token budget are available.

        ``chars`` is treated as a proxy for tokens when no tokenizer is present.
        """
        if self._rpm <= 0 and self._tpm <= 0:
            return

        while True:
            async with self._lock:
                now = time.monotonic()
                self._replenish(now)

                can_request = self._rpm <= 0 or self._request_tokens >= tokens
                can_token = self._tpm <= 0 or self._token_tokens >= chars

                if can_request and can_token:
                    self._request_tokens -= tokens
                    self._token_tokens -= chars
                    return

                wait_request = 0.0
                if self._rpm > 0 and self._request_tokens < tokens:
                    wait_request = (tokens - self._request_tokens) * 60.0 / self._rpm

                wait_token = 0.0
                if self._tpm > 0 and chars > 0 and self._token_tokens < chars:
                    wait_token = (chars - self._token_tokens) * 60.0 / self._tpm

                wait = max(wait_request, wait_token)
                if wait <= 0:
                    wait = 0.05

                # Release the lock while sleeping so other waiters can be served
                # when tokens become available; re-acquire before re-checking.
                self._last_update = now
            await asyncio.sleep(wait)


@lru_cache
def get_extract_rate_limiter() -> AsyncTokenBucket:
    """Return the process-wide extractor rate limiter.

    The limiter is cached so chunked extraction, MVP extraction, and any other
    extract paths share the same RPM/TPM budget.
    """
    from backend.config import get_settings

    settings = get_settings()
    return AsyncTokenBucket(
        rpm=settings.extract_chunk_rpm_limit,
        tpm=settings.extract_chunk_tpm_limit,
    )


def reset_extract_rate_limiter() -> None:
    """Clear the cached limiter (used in tests to pick up monkey-patched env)."""
    limiter = get_extract_rate_limiter
    if hasattr(limiter, "cache_clear"):
        limiter.cache_clear()


@lru_cache
def get_reranker_rate_limiter() -> AsyncTokenBucket:
    """Return the process-wide Reranker QPS limiter.

    ``RERANKER_QPS_LIMIT`` is converted to RPM for ``AsyncTokenBucket``
    (``rpm = int(qps * 60)``). ``tpm`` is unused (pair payloads are tiny).
    ``qps <= 0`` disables throttling.
    """
    from backend.config import get_settings

    settings = get_settings()
    qps = settings.reranker_qps_limit
    rpm = int(qps * 60) if qps > 0 else 0
    return AsyncTokenBucket(rpm=rpm, tpm=0)


def reset_reranker_rate_limiter() -> None:
    """Clear the cached Reranker limiter (tests / settings reload)."""
    limiter = get_reranker_rate_limiter
    if hasattr(limiter, "cache_clear"):
        limiter.cache_clear()
