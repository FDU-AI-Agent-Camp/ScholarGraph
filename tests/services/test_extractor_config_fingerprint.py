# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for extractor config fingerprint."""

from __future__ import annotations

from backend.config import Settings
from backend.services.extractor_config_fingerprint import compute_extractor_config_hash


def test_compute_extractor_config_hash_is_stable() -> None:
    settings = Settings(_env_file=None)
    first = compute_extractor_config_hash(settings)
    second = compute_extractor_config_hash(settings)
    assert first == second
    assert len(first) == 64


def test_compute_extractor_config_hash_changes_with_model() -> None:
    base = Settings(_env_file=None)
    other = base.model_copy(update={"llm_model_primary": "Different-Model"})
    assert compute_extractor_config_hash(base) != compute_extractor_config_hash(other)
