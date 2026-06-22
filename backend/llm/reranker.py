"""Cloud reranker client for fine-grained semantic pair verification."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from backend.config import Settings

logger = logging.getLogger(__name__)


def _default_rerank_timeout() -> float:
    return 60.0


class RerankerClient:
    """Thin async client for an OpenAI-compatible ``/rerank`` endpoint.

    The client consumes pairs of node texts produced by the coarse filter and
    returns a relevance score for each pair.  When reranking is disabled in
    settings, all pairs are treated as homogeneous (score 1.0) so callers can
    keep the same control flow in mock / test environments.
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
                "reranker_disabled: semantic merge fidelity is degraded; "
                "all candidate pairs rejected conservatively"
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

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._base_url(), json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return self._extract_score(data)

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Return reranker scores for multiple pairs, processed in batches.

        The ``RERANKER_BATCH_SIZE`` setting controls how many pairs are kept
        in flight concurrently.  Each pair is still a separate /rerank call
        because standard OpenAI-compatible endpoints use a single query per
        request; the batching only limits concurrency.
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

            for score in batch_scores:
                if isinstance(score, Exception):
                    logger.warning("rerank_pair_failed", extra={"error": str(score)})
                    # Treat failed pairs as non-homogeneous so we do not merge
                    # on uncertain evidence.
                    scores.append(0.0)
                else:
                    scores.append(score)

        return scores
