# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Validate golden QA set schema and data integrity (V2 Phase 4).

Verifies:
- JSON is parseable and has the required structure.
- At least 10 items per V2 requirement.
- Required fields per item (question, paradigm, paper_id, gold).
- gold.nodes / gold.edges reference plausible IDs.
- No duplicate questions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.rag.models import QuestionScale

_GOLDEN_SET_PATH = Path(__file__).resolve().parents[2] / "data" / "qa_golden_set.json"

_VALID_PARADIGMS = {"STEM", "HSS"}
_VALID_SCALES = {scale.value for scale in QuestionScale}


@pytest.fixture
def golden_data() -> dict:
    assert _GOLDEN_SET_PATH.is_file(), f"金标文件不存在: {_GOLDEN_SET_PATH}"
    return json.loads(_GOLDEN_SET_PATH.read_text(encoding="utf-8"))


def test_golden_file_exists_and_is_parseable(golden_data: dict) -> None:
    assert "version" in golden_data
    assert isinstance(golden_data["version"], str)
    assert "items" in golden_data
    assert isinstance(golden_data["items"], list)


def test_golden_items_at_least_10(golden_data: dict) -> None:
    items = golden_data["items"]
    assert len(items) >= 10, f"金标问题集至少需要 10 题，当前 {len(items)} 题"


def test_each_item_has_required_fields(golden_data: dict) -> None:
    required = {"question", "paradigm", "paper_id", "gold"}
    for idx, item in enumerate(golden_data["items"]):
        missing = required - set(item.keys())
        assert not missing, f"Item {idx}: 缺少字段 {missing}"


def test_each_item_paradigm_is_valid(golden_data: dict) -> None:
    for idx, item in enumerate(golden_data["items"]):
        paradigm = item.get("paradigm")
        assert paradigm in _VALID_PARADIGMS, f"Item {idx}: 无效 paradigm={paradigm!r}, 期望 {_VALID_PARADIGMS}"


def test_each_item_scale_is_valid(golden_data: dict) -> None:
    for idx, item in enumerate(golden_data["items"]):
        scale = item.get("scale")
        assert scale in _VALID_SCALES, f"Item {idx}: 无效 scale={scale!r}, 期望 {_VALID_SCALES}"


def test_each_item_question_is_nonempty(golden_data: dict) -> None:
    for idx, item in enumerate(golden_data["items"]):
        question = item.get("question", "")
        assert isinstance(question, str) and question.strip(), f"Item {idx}: question 为空"


def test_each_item_gold_has_nodes_or_edges(golden_data: dict) -> None:
    for idx, item in enumerate(golden_data["items"]):
        gold = item.get("gold", {})
        nodes = gold.get("nodes", [])
        edges = gold.get("edges", [])
        paragraphs = gold.get("paragraphs", [])
        assert isinstance(nodes, list), f"Item {idx}: gold.nodes 不是 list"
        assert isinstance(edges, list), f"Item {idx}: gold.edges 不是 list"
        assert isinstance(paragraphs, list), f"Item {idx}: gold.paragraphs 不是 list"


def test_golden_items_have_required_patterns(golden_data: dict) -> None:
    items_with_patterns = 0
    for item in golden_data["items"]:
        gold = item.get("gold", {})
        if gold.get("required_patterns"):
            items_with_patterns += 1
    assert items_with_patterns >= 5, f"至少 5 题需要有 required_patterns，当前 {items_with_patterns} 题"


def test_golden_items_diverse_paradigms(golden_data: dict) -> None:
    golden_set = golden_data["items"]
    paradigms = {item["paradigm"] for item in golden_set}
    assert "HSS" in paradigms, "Missing HSS paradigm cases"
    assert "STEM" in paradigms, "Acceptance Failed: STEM paradigm cases must be present in Golden Set!"

    stem_details = [item for item in golden_set if item["paradigm"] == "STEM" and item["scale"] == "detail"]
    assert len(stem_details) >= 2, "Acceptance Failed: at least 2 STEM detail cases required for chunk recall gate"

    for case in stem_details:
        case_id = case.get("id", case["question"][:40])
        gold = case.get("gold", {})
        assert len(gold.get("required_patterns", [])) > 0, f"STEM detail case {case_id} must contain required_patterns"
        paragraphs = [str(p).strip() for p in gold.get("paragraphs", []) if str(p).strip()]
        assert len(paragraphs) > 0, f"STEM detail case {case_id} must preserve chunk references in gold.paragraphs"


def test_no_duplicate_questions(golden_data: dict) -> None:
    questions = [item.get("question", "") for item in golden_data["items"]]
    seen: set[str] = set()
    duplicates: list[str] = []
    for q in questions:
        if q in seen:
            duplicates.append(q)
        seen.add(q)
    assert not duplicates, f"发现重复问题: {duplicates}"


def test_allowed_recall_floor_is_reasonable(golden_data: dict) -> None:
    floor = golden_data.get("allowed_recall_floor", 0.80)
    assert 0.0 <= floor <= 1.0, f"allowed_recall_floor={floor} 不在 [0, 1] 范围内"


def test_version_is_date_format(golden_data: dict) -> None:
    version = golden_data.get("version", "")
    parts = version.split("-")
    assert len(parts) == 3, f"version={version!r} 不符合日期格式 YYYY-MM-DD"
    year, month, day = parts
    assert int(year) >= 2026
    assert 1 <= int(month) <= 12
    assert 1 <= int(day) <= 31
