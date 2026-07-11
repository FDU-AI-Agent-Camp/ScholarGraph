"""Load and validate patrol claim-evolution RQ golden pairs (组员 D hardened fixtures)."""

from __future__ import annotations

import json
import math
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "patrol_golden_set.json"
_EXPECTED_PAIR_COUNT = 10
_EXPECTED_STEM_COUNT = 5
_EXPECTED_HSS_COUNT = 5
_EXPECTED_POSITIVE_COUNT = 5
_EXPECTED_NEGATIVE_COUNT = 5


class GoldenPairExpectation(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class GoldenPairMockScores(BaseModel):
    coarse_similarity: float = Field(ge=0.0, le=1.0)
    rerank_score: float = Field(ge=0.0, le=1.0)


class PatrolGoldenPair(BaseModel):
    id: str = Field(min_length=1)
    paradigm: Literal["STEM", "HSS"]
    expectation: GoldenPairExpectation
    label_a: str = Field(min_length=1)
    label_b: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    mock: GoldenPairMockScores


class PatrolGoldenSet(BaseModel):
    schema_version: int
    dataset_id: str
    description: str
    owner: str | None = None
    pairs: list[PatrolGoldenPair]

    @model_validator(mode="after")
    def validate_distribution(self) -> PatrolGoldenSet:
        if len(self.pairs) != _EXPECTED_PAIR_COUNT:
            msg = f"golden set must contain exactly {_EXPECTED_PAIR_COUNT} pairs"
            raise ValueError(msg)

        ids = [pair.id for pair in self.pairs]
        if len(ids) != len(set(ids)):
            raise ValueError("golden pair ids must be unique")

        stem_count = sum(1 for pair in self.pairs if pair.paradigm == "STEM")
        hss_count = sum(1 for pair in self.pairs if pair.paradigm == "HSS")
        if stem_count != _EXPECTED_STEM_COUNT or hss_count != _EXPECTED_HSS_COUNT:
            msg = (
                f"expected STEM={_EXPECTED_STEM_COUNT} HSS={_EXPECTED_HSS_COUNT}, got STEM={stem_count} HSS={hss_count}"
            )
            raise ValueError(msg)

        positive_count = sum(1 for pair in self.pairs if pair.expectation == GoldenPairExpectation.POSITIVE)
        negative_count = sum(1 for pair in self.pairs if pair.expectation == GoldenPairExpectation.NEGATIVE)
        if positive_count != _EXPECTED_POSITIVE_COUNT or negative_count != _EXPECTED_NEGATIVE_COUNT:
            msg = (
                f"expected positive={_EXPECTED_POSITIVE_COUNT} negative={_EXPECTED_NEGATIVE_COUNT}, "
                f"got positive={positive_count} negative={negative_count}"
            )
            raise ValueError(msg)

        return self


@lru_cache(maxsize=1)
def load_patrol_golden_set() -> PatrolGoldenSet:
    """Load and validate ``data/patrol_golden_set.json``."""
    raw = json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return PatrolGoldenSet.model_validate(raw)


def golden_set_path() -> Path:
    return _GOLDEN_SET_PATH


def _vectors_for_target_cosine(similarity: float) -> tuple[list[float], list[float]]:
    clamped = max(-1.0, min(1.0, similarity))
    left = [1.0, 0.0]
    right = [clamped, math.sqrt(max(0.0, 1.0 - clamped**2))]
    return left, right


class GoldenPairEmbeddingClient:
    """Deterministic embedding client driven by golden-set mock coarse scores."""

    is_mock = False

    def __init__(self, pair: PatrolGoldenPair) -> None:
        self._pair = pair
        left, right = _vectors_for_target_cosine(pair.mock.coarse_similarity)
        self._vectors = {
            pair.label_a: left,
            pair.label_b: right,
        }

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors.get(text, [0.0, 0.0]).copy() for text in texts]


class GoldenPairRerankerClient:
    """Deterministic reranker client driven by golden-set mock rerank scores."""

    def __init__(self, pair: PatrolGoldenPair) -> None:
        self._score = pair.mock.rerank_score

    async def rerank_pair(self, text_a: str, text_b: str) -> float:
        return self._score

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [self._score for _ in pairs]
