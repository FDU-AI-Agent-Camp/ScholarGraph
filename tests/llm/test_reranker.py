# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for the cloud reranker client."""

from __future__ import annotations

import pytest
from backend.config import Settings
from backend.llm.reranker import RerankerClient


def _settings(enabled: bool = True, model: str = "bge-reranker-v2-m3") -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        reranker_enabled=enabled,
        reranker_model=model,
        reranker_api_base_url="https://api.example.com/v1",
        reranker_api_key="fake-key",
    )


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
