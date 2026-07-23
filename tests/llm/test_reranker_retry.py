# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for Reranker tenacity retry and transient error classification."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from backend.llm.reranker_retry import is_transient_rerank_error, run_with_rerank_retry


@pytest.fixture(autouse=True)
def _fast_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)


def test_is_transient_rerank_error_detects_http_status() -> None:
    request = httpx.Request("POST", "https://example.com/rerank")
    response_429 = httpx.Response(429, request=request)
    response_503 = httpx.Response(503, request=request)
    response_400 = httpx.Response(400, request=request)
    assert is_transient_rerank_error(httpx.HTTPStatusError("limited", request=request, response=response_429))
    assert is_transient_rerank_error(httpx.HTTPStatusError("unavailable", request=request, response=response_503))
    assert not is_transient_rerank_error(httpx.HTTPStatusError("bad", request=request, response=response_400))


def test_is_transient_rerank_error_detects_request_error_and_markers() -> None:
    request = httpx.Request("POST", "https://example.com/rerank")
    assert is_transient_rerank_error(httpx.ConnectError("boom", request=request))
    assert is_transient_rerank_error(httpx.ConnectTimeout("timed out", request=request))
    assert is_transient_rerank_error(RuntimeError("ModelArts.81101 rate limit"))
    assert not is_transient_rerank_error(ValueError("invalid json schema"))


def test_is_transient_rerank_error_rejects_401_and_400() -> None:
    request = httpx.Request("POST", "https://example.com/rerank")
    err_401 = httpx.HTTPStatusError(
        "unauthorized",
        request=request,
        response=httpx.Response(401, request=request),
    )
    err_400 = httpx.HTTPStatusError(
        "bad request",
        request=request,
        response=httpx.Response(400, request=request),
    )
    assert not is_transient_rerank_error(err_401)
    assert not is_transient_rerank_error(err_400)


@pytest.mark.asyncio
async def test_run_with_rerank_retry_recovers_after_transient_failures() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("429 rate limit exceeded")
        return "ok"

    result = await run_with_rerank_retry(flaky)
    assert result == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_run_with_rerank_retry_does_not_retry_deterministic_errors() -> None:
    attempts = 0

    async def broken() -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("schema validation failed")

    with pytest.raises(ValueError, match="schema validation failed"):
        await run_with_rerank_retry(broken)
    assert attempts == 1
