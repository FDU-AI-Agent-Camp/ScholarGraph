# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Cloud reranker client for fine-grained semantic pair verification."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from backend.config import Settings
from backend.llm.rate_limiter import get_reranker_rate_limiter
from backend.llm.reranker_retry import run_with_rerank_retry

logger = logging.getLogger(__name__)

_DEFAULT_RERANK_TIMEOUT_SECONDS = 60.0
_HTTP_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)

_http_client: httpx.AsyncClient | None = None
_http_client_lock: asyncio.Lock | None = None
_semaphore: asyncio.Semaphore | None = None
_semaphore_limit: int | None = None
_semaphore_lock: asyncio.Lock | None = None


def _default_rerank_timeout() -> float:
    return _DEFAULT_RERANK_TIMEOUT_SECONDS


def _ensure_lock(lock: asyncio.Lock | None) -> asyncio.Lock:
    """Create asyncio locks lazily so they bind to the running event loop."""
    if lock is None:
        return asyncio.Lock()
    return lock


def get_reranker_http_client() -> httpx.AsyncClient:
    """Return a process-wide shared AsyncClient (connection pool reuse).

    Prefer ``ensure_reranker_http_client`` from async code for race-free init.
    """
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=_default_rerank_timeout(),
            limits=_HTTP_LIMITS,
        )
    return _http_client


async def ensure_reranker_http_client() -> httpx.AsyncClient:
    """Async-safe accessor for the shared Reranker HTTP client."""
    global _http_client, _http_client_lock
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    _http_client_lock = _ensure_lock(_http_client_lock)
    async with _http_client_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=_default_rerank_timeout(),
                limits=_HTTP_LIMITS,
            )
        return _http_client


async def _get_reranker_semaphore(limit: int) -> asyncio.Semaphore:
    """Lazy module-level semaphore sized by ``RERANKER_CONCURRENCY_LIMIT``."""
    global _semaphore, _semaphore_limit, _semaphore_lock
    _semaphore_lock = _ensure_lock(_semaphore_lock)
    async with _semaphore_lock:
        if _semaphore is None or _semaphore_limit != limit:
            _semaphore = asyncio.Semaphore(limit)
            _semaphore_limit = limit
        return _semaphore


def reset_reranker_http_state() -> None:
    """Drop shared client / semaphore / locks (tests)."""
    global _http_client, _http_client_lock, _semaphore, _semaphore_limit, _semaphore_lock
    _http_client = None
    _http_client_lock = None
    _semaphore = None
    _semaphore_limit = None
    _semaphore_lock = None


class RerankerClient:
    """Thin async client for an OpenAI-compatible ``/rerank`` endpoint.

    The client consumes pairs of node texts produced by the coarse filter and
    returns a relevance score for each pair.  When reranking is disabled in
    settings, all pairs are rejected conservatively (score 0.0).

    Rate limiting, concurrency, and the HTTP pool live at module scope because
    ``RerankerClient`` instances are short-lived (created per clustering call).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        from backend.config import get_settings

        self._settings = settings or get_settings()
        self._timeout = _default_rerank_timeout()

    def _base_url(self) -> str:
        base = self._settings.reranker_api_base_url_effective
        if not base:
            msg = "缺少 Reranker API 基地址：请在 .env 中设置 RERANKER_API_BASE_URL 或 LLM_API_BASE_URL"
            raise ValueError(msg)
        return base.rstrip("/") + "/rerank"

    def _api_key(self) -> str:
        return self._settings.reranker_api_key_effective

    def _model(self) -> str:
        model = self._settings.reranker_model.strip()
        if not model:
            msg = "缺少 Reranker 模型名：请在 .env 中设置 RERANKER_MODEL"
            raise ValueError(msg)
        return model

    @staticmethod
    def _extract_score(data: dict[str, Any]) -> float:
        """Extract the first relevance score from a reranker response."""
        results = data.get("results")
        if results is None:
            results = data.get("data", [])
        if results and isinstance(results, list):
            first = results[0]
            if isinstance(first, dict):
                score = first.get("relevance_score") or first.get("score")
                if score is not None:
                    return float(score)
        if "scores" in data and isinstance(data["scores"], list):
            return float(data["scores"][0])
        msg = f"Unexpected reranker response shape: {list(data.keys())}"
        raise ValueError(msg)

    async def _post_rerank(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        client = await ensure_reranker_http_client()
        response = await client.post(self._base_url(), json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            msg = f"Unexpected reranker response type: {type(data).__name__}"
            raise ValueError(msg)
        return data

    async def rerank_pair(self, text_a: str, text_b: str) -> float:
        """Return the reranker relevance score for a single (query, document) pair.

        When reranking is disabled we return 0.0 instead of 1.0.  Returning 1.0
        would silently turn off the fine-filter and cause every coarse candidate
        pair to be merged, reproducing the pre-refactor over-merging behavior.
        Returning 0.0 is the conservative fallback: no pair is promoted to
        TRUE_HOMOGENEOUS without explicit verification.
        """
        if not self._settings.reranker_enabled:
            logger.warning(
                "reranker_disabled: semantic merge fidelity is degraded; all candidate pairs rejected conservatively"
            )
            return 0.0

        payload: dict[str, Any] = {
            "model": self._model(),
            "query": text_a,
            "documents": [text_b],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

        await get_reranker_rate_limiter().acquire(tokens=1, chars=0)
        semaphore = await _get_reranker_semaphore(self._settings.reranker_concurrency_limit)
        async with semaphore:

            async def _once() -> dict[str, Any]:
                return await self._post_rerank(payload, headers)

            data = await run_with_rerank_retry(_once)
        return self._extract_score(data)

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Return reranker scores for multiple pairs, processed in batches.

        The ``RERANKER_BATCH_SIZE`` setting controls how many pairs are kept
        in flight concurrently.  Each pair is still a separate /rerank call
        because standard OpenAI-compatible endpoints use a single query per
        request; the batching only limits concurrency.  Process-wide QPS and
        semaphore gates inside ``rerank_pair`` further smooth MaaS pressure.
        """
        if not self._settings.reranker_enabled:
            logger.warning(
                "reranker_disabled: semantic merge fidelity is degraded; "
                "all %d candidate pairs rejected conservatively",
                len(pairs),
            )
            return [0.0] * len(pairs)
        if not pairs:
            return []

        batch_size = max(1, self._settings.reranker_batch_size)
        scores: list[float] = []

        for offset in range(0, len(pairs), batch_size):
            batch = pairs[offset : offset + batch_size]
            coros = [self.rerank_pair(a, b) for a, b in batch]
            batch_scores = await asyncio.gather(*coros, return_exceptions=True)

            for index, score in enumerate(batch_scores):
                if isinstance(score, BaseException):
                    logger.warning(
                        "rerank_pair_failed",
                        extra={
                            "error": str(score),
                            "error_type": type(score).__name__,
                            "pair_index": offset + index,
                        },
                        exc_info=score,
                    )
                    # Treat failed pairs as non-homogeneous so we do not merge
                    # on uncertain evidence.
                    scores.append(0.0)
                else:
                    scores.append(score)

        return scores
