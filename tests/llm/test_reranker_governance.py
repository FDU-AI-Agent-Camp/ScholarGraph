# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Governance tests for Reranker retry / QPS / semaphore / boundary behavior (SC-R1)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from backend.config import Settings
from backend.llm.rate_limiter import AsyncTokenBucket, reset_reranker_rate_limiter
from backend.llm.reranker import RerankerClient, reset_reranker_http_state
from backend.llm.reranker_retry import RERANK_RETRY_WAIT, is_transient_rerank_error
from tenacity import wait_exponential


_RERANK_URL = "https://api.example.com/v1/rerank"


def _settings(
    *,
    enabled: bool = True,
    batch_size: int = 4,
    concurrency: int = 2,
    qps: float = 0.0,
    max_retries: int = 3,
) -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        reranker_enabled=enabled,
        reranker_model="bge-reranker-v2-m3",
        reranker_api_base_url="https://api.example.com/v1",
        reranker_api_key="fake-key",
        reranker_batch_size=batch_size,
        reranker_concurrency_limit=concurrency,
        reranker_qps_limit=qps,
        reranker_max_retries=max_retries,
    )


def _ok_response(score: float = 0.92) -> httpx.Response:
    return httpx.Response(
        200,
        json={"results": [{"index": 0, "relevance_score": score}]},
        request=httpx.Request("POST", _RERANK_URL),
    )


def _status_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"error": "ModelArts.81101"},
        request=httpx.Request("POST", _RERANK_URL),
    )


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("RERANKER_QPS_LIMIT", "0")
    monkeypatch.setenv("RERANKER_MAX_RETRIES", "3")
    from backend.config import get_settings

    get_settings.cache_clear()
    reset_reranker_rate_limiter()
    reset_reranker_http_state()
    yield
    reset_reranker_rate_limiter()
    reset_reranker_http_state()
    get_settings.cache_clear()


def _patch_http(mock_http: AsyncMock):
    return patch(
        "backend.llm.reranker.ensure_reranker_http_client",
        AsyncMock(return_value=mock_http),
    )


# ---------------------------------------------------------------------------
# I. Retry matrix (client path)
# ---------------------------------------------------------------------------


class TestRerankerRetryMatrix:
    @pytest.fixture(autouse=True)
    def _fast_retry_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _instant(_delay: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", _instant)

    async def test_rerank_pair_recovers_after_two_429s(self, caplog: pytest.LogCaptureFixture) -> None:
        client = RerankerClient(_settings())
        responses = [_status_response(429), _status_response(429), _ok_response(0.92)]
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=responses)

        with caplog.at_level(logging.WARNING), _patch_http(mock_http):
            score = await client.rerank_pair("nodeA", "nodeB")

        assert score == pytest.approx(0.92)
        assert mock_http.post.await_count == 3
        assert any("Retrying" in record.message or "retry" in record.message.lower() for record in caplog.records)

    async def test_rerank_pair_fail_fast_on_401(self) -> None:
        client = RerankerClient(_settings())
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=_status_response(401))

        with _patch_http(mock_http), pytest.raises(httpx.HTTPStatusError) as err:
            await client.rerank_pair("nodeA", "nodeB")

        assert err.value.response.status_code == 401
        assert mock_http.post.await_count == 1

    async def test_rerank_pairs_fail_fast_401_degrades_item_to_zero(self) -> None:
        client = RerankerClient(_settings())
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=_status_response(401))

        with _patch_http(mock_http):
            scores = await client.rerank_pairs([("a", "b"), ("c", "d")])

        assert scores == [0.0, 0.0]
        assert mock_http.post.await_count == 2

    async def test_rerank_pairs_exhausts_retries_then_returns_zero(self) -> None:
        client = RerankerClient(_settings(max_retries=3))
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=_status_response(429))

        with _patch_http(mock_http):
            scores = await client.rerank_pairs([("a", "b")])

        assert scores == [0.0]
        assert mock_http.post.await_count == 3

    async def test_rerank_pair_retries_connect_timeout_then_succeeds(self) -> None:
        client = RerankerClient(_settings())
        request = httpx.Request("POST", _RERANK_URL)
        timeout = httpx.ConnectTimeout("connect timed out", request=request)
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=[timeout, timeout, _ok_response(0.88)])

        with _patch_http(mock_http):
            score = await client.rerank_pair("a", "b")

        assert score == pytest.approx(0.88)
        assert mock_http.post.await_count == 3
        assert is_transient_rerank_error(timeout) is True


# ---------------------------------------------------------------------------
# II. QPS + concurrency
# ---------------------------------------------------------------------------


class TestRerankerRateAndConcurrency:
    async def test_qps_limiter_paces_after_burst_capacity_depleted(self) -> None:
        """Token bucket allows an initial burst of ``rpm``; pacing applies after depletion.

        ``RERANKER_QPS_LIMIT=3`` → rpm=180. Deplete burst, then 12 acquires need ≥3s
        at 3 QPS refill.
        """
        monkey_bucket = AsyncTokenBucket(rpm=180, tpm=0)
        await monkey_bucket.acquire(tokens=180)

        client = RerankerClient(_settings(qps=3.0, concurrency=8, batch_size=12))
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=_ok_response(0.9))
        timestamps: list[float] = []

        async def _post(_url: str, **_kwargs: object) -> httpx.Response:
            timestamps.append(time.monotonic())
            return _ok_response(0.9)

        mock_http.post = AsyncMock(side_effect=_post)

        with (
            patch("backend.llm.reranker.get_reranker_rate_limiter", return_value=monkey_bucket),
            _patch_http(mock_http),
        ):
            started = time.monotonic()
            scores = await client.rerank_pairs([(f"a{i}", f"b{i}") for i in range(12)])
            elapsed = time.monotonic() - started

        assert len(scores) == 12
        assert all(s == pytest.approx(0.9) for s in scores)
        assert elapsed >= 3.0
        assert mock_http.post.await_count == 12
        # No instantaneous 12-way flush after depletion: span of call times ≥ 3s.
        assert timestamps[-1] - timestamps[0] >= 3.0

    async def test_semaphore_caps_in_flight_http_requests(self) -> None:
        client = RerankerClient(_settings(concurrency=2, batch_size=8, qps=0.0))
        in_flight = 0
        max_in_flight = 0
        lock = asyncio.Lock()

        async def _slow_post(_url: str, **_kwargs: object) -> httpx.Response:
            nonlocal in_flight, max_in_flight
            async with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.05)
            async with lock:
                in_flight -= 1
            return _ok_response(0.85)

        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=_slow_post)

        with _patch_http(mock_http):
            scores = await client.rerank_pairs([(f"a{i}", f"b{i}") for i in range(8)])

        assert len(scores) == 8
        assert max_in_flight <= 2


# ---------------------------------------------------------------------------
# III. Boundary / defense
# ---------------------------------------------------------------------------


class TestRerankerBoundaries:
    async def test_empty_pairs_skips_http_and_rate_limiter(self) -> None:
        client = RerankerClient(_settings())
        acquire = AsyncMock()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock()

        with (
            patch("backend.llm.reranker.get_reranker_rate_limiter") as get_limiter,
            _patch_http(mock_http),
        ):
            get_limiter.return_value.acquire = acquire
            result = await client.rerank_pairs([])

        assert result == []
        acquire.assert_not_awaited()
        mock_http.post.assert_not_awaited()

    async def test_large_pair_set_batches_without_crash(self) -> None:
        client = RerankerClient(_settings(batch_size=4, concurrency=2, qps=0.0))
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=_ok_response(0.7))

        pairs = [(f"q{i}", f"d{i}") for i in range(100)]
        with _patch_http(mock_http):
            scores = await client.rerank_pairs(pairs)

        assert len(scores) == 100
        assert mock_http.post.await_count == 100

    async def test_disabled_reranker_does_not_consume_rate_tokens(self) -> None:
        client = RerankerClient(_settings(enabled=False))
        acquire = AsyncMock()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock()

        with (
            patch("backend.llm.reranker.get_reranker_rate_limiter") as get_limiter,
            _patch_http(mock_http),
        ):
            get_limiter.return_value.acquire = acquire
            score = await client.rerank_pair("a", "b")
            scores = await client.rerank_pairs([("a", "b")])

        assert score == 0.0
        assert scores == [0.0]
        acquire.assert_not_awaited()
        mock_http.post.assert_not_awaited()

    def test_retry_wait_is_exponential_without_random_jitter(self) -> None:
        """SC-R1 aligns with Judge: deterministic exponential wait (no wait_random_exponential)."""
        assert isinstance(RERANK_RETRY_WAIT, wait_exponential)

    async def test_long_payload_is_serialized_in_json_body(self) -> None:
        client = RerankerClient(_settings())
        long_text = "论点" * 5_000 + "\n特殊字符<>&\"'"
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=_ok_response(0.5))

        with _patch_http(mock_http):
            score = await client.rerank_pair(long_text, long_text[::-1])

        assert score == pytest.approx(0.5)
        payload = mock_http.post.await_args.kwargs["json"]
        assert payload["query"] == long_text
        assert payload["documents"] == [long_text[::-1]]


# ---------------------------------------------------------------------------
# IV. Observability note — before_sleep WARNING
# ---------------------------------------------------------------------------


class TestRerankerObservability:
    @pytest.fixture(autouse=True)
    def _fast_retry_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _instant(_delay: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", _instant)

    async def test_before_sleep_emits_warning_on_429(self, caplog: pytest.LogCaptureFixture) -> None:
        client = RerankerClient(_settings())
        mock_http = AsyncMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=[_status_response(429), _ok_response(0.8)])

        with caplog.at_level(logging.WARNING, logger="backend.llm.reranker_retry"), _patch_http(mock_http):
            score = await client.rerank_pair("a", "b")

        assert score == pytest.approx(0.8)
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_messages, "expected tenacity before_sleep_log WARNING"
        joined = " ".join(warning_messages).lower()
        assert "retrying" in joined or "attempt" in joined
