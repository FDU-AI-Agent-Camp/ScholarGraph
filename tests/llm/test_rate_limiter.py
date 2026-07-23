# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for the async token-bucket rate limiter (Slice 2)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from backend.llm.rate_limiter import AsyncTokenBucket


class TestAsyncTokenBucket:
    async def test_disabled_limiter_returns_immediately(self) -> None:
        bucket = AsyncTokenBucket(rpm=0, tpm=0)
        start = datetime.now(UTC)
        await bucket.acquire(tokens=1, chars=1_000_000)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed < 0.1

    async def test_rpm_limit_throttles_requests(self) -> None:
        # 120 RPM bucket starts with 120 tokens. Deplete them, then one more waits.
        bucket = AsyncTokenBucket(rpm=120, tpm=0)
        await bucket.acquire(tokens=120)
        start = datetime.now(UTC)
        await bucket.acquire(tokens=1)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.3

    async def test_tpm_limit_throttles_by_chars(self) -> None:
        # 120 TPM bucket starts with 120 tokens. Deplete them, then one more waits.
        bucket = AsyncTokenBucket(rpm=0, tpm=120)
        await bucket.acquire(chars=120)
        start = datetime.now(UTC)
        await bucket.acquire(chars=1)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.3

    async def test_acquire_decrements_tokens(self) -> None:
        bucket = AsyncTokenBucket(rpm=120, tpm=240)
        await bucket.acquire(tokens=120, chars=120)
        # Remaining: 0 request tokens, 120 token tokens. Next request waits.
        start = datetime.now(UTC)
        await bucket.acquire(tokens=1, chars=0)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.3

    async def test_concurrent_acquires_stay_within_rate(self) -> None:
        bucket = AsyncTokenBucket(rpm=120, tpm=0)  # 2 per second, capacity 120
        start = datetime.now(UTC)

        async def _worker() -> None:
            await bucket.acquire(tokens=1)

        # 121 workers: 120 tokens available immediately, the 121st waits 0.5s.
        await asyncio.gather(*(_worker() for _ in range(121)))
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.3

    async def test_zero_chars_skips_token_check(self) -> None:
        bucket = AsyncTokenBucket(rpm=0, tpm=60)
        await bucket.acquire(tokens=1, chars=0)

    async def test_negative_limits_are_clamped_to_zero(self) -> None:
        bucket = AsyncTokenBucket(rpm=-10, tpm=-5)
        start = datetime.now(UTC)
        await bucket.acquire(tokens=1_000_000, chars=1_000_000)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed < 0.1

    async def test_replenish_never_exceeds_capacity(self) -> None:
        bucket = AsyncTokenBucket(rpm=60, tpm=0)
        await bucket.acquire(tokens=60)
        await asyncio.sleep(1.2)
        await bucket.acquire(tokens=60)
        # After two full depletions separated by >1 minute, capacity should still
        # be capped at 60, not accumulated indefinitely.
        assert bucket._request_tokens <= 60

    async def test_tpm_with_large_chars_blocks_until_refill(self) -> None:
        bucket = AsyncTokenBucket(rpm=0, tpm=60)
        await bucket.acquire(chars=60)
        start = datetime.now(UTC)
        await bucket.acquire(chars=30)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.3

    async def test_concurrent_waiters_do_not_starve(self) -> None:
        bucket = AsyncTokenBucket(rpm=120, tpm=0)
        await bucket.acquire(tokens=120)
        completed = []

        async def _worker(index: int) -> None:
            await bucket.acquire(tokens=1)
            completed.append(index)

        await asyncio.gather(*(_worker(i) for i in range(5)))
        assert len(completed) == 5

    async def test_zero_tokens_only_checks_character_budget(self) -> None:
        bucket = AsyncTokenBucket(rpm=60, tpm=60)
        await bucket.acquire(tokens=60, chars=60)
        start = datetime.now(UTC)
        await bucket.acquire(tokens=0, chars=1)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.3

    async def test_get_reranker_rate_limiter_maps_qps_to_rpm(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from backend.config import get_settings
        from backend.llm.rate_limiter import get_reranker_rate_limiter, reset_reranker_rate_limiter

        monkeypatch.setenv("RERANKER_QPS_LIMIT", "3.0")
        get_settings.cache_clear()
        reset_reranker_rate_limiter()
        bucket = get_reranker_rate_limiter()
        assert bucket.rpm == 180
        assert bucket.tpm == 0
        reset_reranker_rate_limiter()
        get_settings.cache_clear()
