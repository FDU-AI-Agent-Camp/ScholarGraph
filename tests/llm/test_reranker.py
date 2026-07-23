# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for the cloud reranker client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from backend.config import Settings
from backend.llm.rate_limiter import reset_reranker_rate_limiter
from backend.llm.reranker import RerankerClient, reset_reranker_http_state


def _settings(
    enabled: bool = True,
    model: str = "bge-reranker-v2-m3",
    *,
    batch_size: int = 4,
    concurrency: int = 2,
    qps: float = 0.0,
    max_retries: int = 3,
) -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        reranker_enabled=enabled,
        reranker_model=model,
        reranker_api_base_url="https://api.example.com/v1",
        reranker_api_key="fake-key",
        reranker_batch_size=batch_size,
        reranker_concurrency_limit=concurrency,
        reranker_qps_limit=qps,
        reranker_max_retries=max_retries,
    )


@pytest.fixture(autouse=True)
def _reset_reranker_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
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


class TestRerankerClientDisabled:
    async def test_rerank_pair_returns_zero_when_disabled(self) -> None:
        client = RerankerClient(_settings(enabled=False))
        score = await client.rerank_pair("a", "b")
        assert score == 0.0

    async def test_rerank_pairs_returns_all_zeros_when_disabled(self) -> None:
        client = RerankerClient(_settings(enabled=False))
        scores = await client.rerank_pairs([("a", "b"), ("c", "d")])
        assert scores == [0.0, 0.0]


class TestRerankerClientExtractScore:
    def test_extract_score_from_results(self) -> None:
        data = {"results": [{"index": 0, "relevance_score": 0.92}]}
        assert RerankerClient._extract_score(data) == pytest.approx(0.92)

    def test_extract_score_from_data(self) -> None:
        data = {"data": [{"index": 0, "score": 0.88}]}
        assert RerankerClient._extract_score(data) == pytest.approx(0.88)

    def test_extract_score_from_scores_array(self) -> None:
        data = {"scores": [0.75]}
        assert RerankerClient._extract_score(data) == pytest.approx(0.75)

    def test_extract_score_raises_on_unknown_shape(self) -> None:
        with pytest.raises(ValueError):
            RerankerClient._extract_score({"unexpected": []})


class TestRerankerClientEmptyInput:
    async def test_rerank_pairs_empty_returns_empty(self) -> None:
        client = RerankerClient(_settings())
        assert await client.rerank_pairs([]) == []


class TestRerankerClientHttp:
    @pytest.fixture(autouse=True)
    def _fast_retry_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _instant(_delay: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", _instant)

    async def test_rerank_pair_posts_and_parses_score(self) -> None:
        client = RerankerClient(_settings())
        mock_response = httpx.Response(
            200,
            json={"results": [{"relevance_score": 0.91}]},
            request=httpx.Request("POST", "https://api.example.com/v1/rerank"),
        )
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False

        with patch("backend.llm.reranker.ensure_reranker_http_client", AsyncMock(return_value=mock_http)):
            score = await client.rerank_pair("query text", "doc text")

        assert score == pytest.approx(0.91)
        mock_http.post.assert_awaited_once()
        call_kwargs = mock_http.post.await_args
        assert call_kwargs.args[0].endswith("/rerank")
        assert call_kwargs.kwargs["json"]["query"] == "query text"

    async def test_rerank_pairs_fallback_zero_after_retries_exhausted(self) -> None:
        client = RerankerClient(_settings())
        request = httpx.Request("POST", "https://api.example.com/v1/rerank")
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError("rate limited", request=request, response=response)

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=error)
        mock_http.is_closed = False

        with patch("backend.llm.reranker.ensure_reranker_http_client", AsyncMock(return_value=mock_http)):
            scores = await client.rerank_pairs([("a", "b")])

        assert scores == [0.0]
        assert mock_http.post.await_count == 3
