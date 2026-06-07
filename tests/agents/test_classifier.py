"""Tests for BE-2 paradigm classifier."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path

import pytest
from backend.agents import classify
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas import Paradigm

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _mock_llm_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()


def run_async(coro):
    return asyncio.run(coro)


def fixture_classifier_inputs() -> dict[str, str]:
    with (REPO_ROOT / "docs/v1/eval/classifier_labels.csv").open(newline="", encoding="utf-8") as labels_file:
        rows = list(csv.DictReader(labels_file))
    return {row["paper_id"]: f"Title: {row['title']}" for row in rows}


def test_classifies_stem_experiment_text() -> None:
    result = run_async(
        classify(
            "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
            "F1 metrics, baselines, and ablation experiments."
        )
    )

    assert result.classification.paradigm == Paradigm.STEM.value
    assert 0 <= result.classification.confidence <= 1
    assert result.classification.reason
    assert result.warnings == []


def test_classifies_hss_theory_text() -> None:
    result = run_async(
        classify("标题：平台零工经济与劳动者心理。本文通过访谈材料和公共领域理论视角，分析劳动者经验并修正既有研究。")
    )

    assert result.classification.paradigm == Paradigm.HSS.value
    assert 0 <= result.classification.confidence <= 1
    assert "HSS" in result.classification.reason or "Mock" in result.classification.reason
    assert result.warnings == []


def test_fixture_labels_are_three_for_three() -> None:
    inputs = fixture_classifier_inputs()
    with (REPO_ROOT / "docs/v1/eval/classifier_labels.csv").open(newline="", encoding="utf-8") as labels_file:
        rows = list(csv.DictReader(labels_file))

    predictions = {
        row["paper_id"]: run_async(classify(inputs[row["paper_id"]])).classification.paradigm.value for row in rows
    }

    assert predictions == {row["paper_id"]: row["paradigm_gold"] for row in rows}
