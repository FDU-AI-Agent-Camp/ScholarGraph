# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Deterministic embedding stubs for method_overlap benchmark dry-run."""

from __future__ import annotations

import math

_LIVE_NB_LR_NOISE_COSINE = 0.90
_NB_NOISE_VECTOR = [1.0, 0.0]
_LR_NOISE_VECTOR = [_LIVE_NB_LR_NOISE_COSINE, math.sqrt(1.0 - _LIVE_NB_LR_NOISE_COSINE**2)]


class GoldenPcaEmbeddingClient:
    """Deterministic vectors for PCA ↔ Principal Component Analysis (not is_mock)."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: dict[str, list[float]] = {}
        for text in texts:
            if text.startswith("PCA") or text.startswith("PCA "):
                vectors[text] = [1.0, 0.0, 0.0]
            elif "Principal Component Analysis" in text:
                vectors[text] = [0.99, 0.01, 0.0]
            else:
                vectors[text] = [0.0, 0.0, 1.0]
        return [vectors.get(text, [0.0, 0.0, 0.0]).copy() for text in texts]


class NbLrNoiseEmbeddingClient:
    """Live false-positive pair: NB ↔ LR cosine ≈ 0.90; disjoint RQ vectors."""

    is_mock = False

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if text.startswith("Naive Bayes"):
                vectors.append(_NB_NOISE_VECTOR.copy())
            elif text.startswith("Logistic Regression"):
                vectors.append(_LR_NOISE_VECTOR.copy())
            else:
                vectors.append([0.0, 0.0])
        return vectors
