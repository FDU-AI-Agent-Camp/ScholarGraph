"""Tests for BE-2 paradigm classifier."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

from backend.agents import classify
from backend.schemas import Paradigm

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_async(coro):
    return asyncio.run(coro)


def fixture_classifier_inputs() -> dict[str, str]:
    payload = json.loads((REPO_ROOT / "docs/api/fixtures/papers-list.json").read_text(encoding="utf-8"))
    return {item["paper_id"]: f"Title: {item['title']}" for item in payload["data"]["items"]}


def test_classifies_stem_experiment_text() -> None:
    result = run_async(
        classify(
            "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
            "F1 metrics, baselines, and ablation experiments."
        )
    )

    assert result.paradigm == Paradigm.STEM.value
    assert 0 <= result.confidence <= 1
    assert result.reason


def test_classifies_hss_theory_text() -> None:
    result = run_async(
        classify("标题：平台零工经济与劳动者心理。本文通过访谈材料和公共领域理论视角，分析劳动者经验并修正既有研究。")
    )

    assert result.paradigm == Paradigm.HSS.value
    assert 0 <= result.confidence <= 1
    assert "HSS" in result.reason


def test_fixture_labels_are_three_for_three() -> None:
    inputs = fixture_classifier_inputs()
    with (REPO_ROOT / "docs/v1/eval/classifier_labels.csv").open(newline="", encoding="utf-8") as labels_file:
        rows = list(csv.DictReader(labels_file))

    predictions = {row["paper_id"]: run_async(classify(inputs[row["paper_id"]])).paradigm for row in rows}

    assert predictions == {row["paper_id"]: row["paradigm_gold"] for row in rows}
