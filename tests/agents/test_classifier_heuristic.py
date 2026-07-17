# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for keyword-heuristic paradigm classification (Phase G fallback)."""

from backend.agents.classifier_heuristic import classify_heuristic
from backend.schemas.paradigm import Paradigm

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)
HSS_SAMPLE = "标题：平台零工经济与劳动者心理。本文通过访谈材料和公共领域理论视角，分析劳动者经验并修正既有研究。"


def test_heuristic_classifies_stem_experiment_text() -> None:
    result = classify_heuristic(STEM_SAMPLE)
    assert result.paradigm == Paradigm.STEM
    assert 0 <= result.confidence <= 1
    assert result.reason


def test_heuristic_classifies_hss_theory_text() -> None:
    result = classify_heuristic(HSS_SAMPLE)
    assert result.paradigm == Paradigm.HSS
    assert 0 <= result.confidence <= 1
    assert "HSS" in result.reason


def test_heuristic_returns_valid_paradigm_classification_shape() -> None:
    result = classify_heuristic(STEM_SAMPLE)
    dumped = result.model_dump(mode="json")
    assert set(dumped.keys()) == {"paradigm", "confidence", "reason"}
    assert dumped["paradigm"] in ("STEM", "HSS")
    assert isinstance(dumped["confidence"], float)
    assert isinstance(dumped["reason"], str) and dumped["reason"].strip()
