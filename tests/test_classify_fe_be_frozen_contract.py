# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Cross-stack frozen contract: backend constants ↔ frontend classifyWarnings.ts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FE_CLASSIFY_WARNINGS = REPO_ROOT / "frontend" / "src" / "utils" / "classifyWarnings.ts"
FIXTURES_DIR = REPO_ROOT / "docs" / "api" / "fixtures"

FROZEN_CODE = "classifier_heuristic_fallback"
FROZEN_MESSAGE = "触发分类启发式Fallback!"


def _read_frontend_classify_constants() -> tuple[str, str]:
    text = FE_CLASSIFY_WARNINGS.read_text(encoding="utf-8")
    code_match = re.search(r"CLASSIFIER_HEURISTIC_FALLBACK_CODE = '([^']+)'", text)
    message_match = re.search(r"CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE = '([^']+)'", text)
    assert code_match is not None, "frontend CLASSIFIER_HEURISTIC_FALLBACK_CODE not found"
    assert message_match is not None, "frontend CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE not found"
    return code_match.group(1), message_match.group(1)


def test_fe_be_classifier_heuristic_fallback_code_matches() -> None:
    fe_code, _ = _read_frontend_classify_constants()
    assert fe_code == CLASSIFIER_HEURISTIC_FALLBACK_CODE == FROZEN_CODE


def test_fe_be_classifier_heuristic_fallback_message_matches() -> None:
    _, fe_message = _read_frontend_classify_constants()
    assert fe_message == CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE == FROZEN_MESSAGE


def test_fe_classify_warnings_maps_code_to_frozen_message() -> None:
    text = FE_CLASSIFY_WARNINGS.read_text(encoding="utf-8")
    assert "[CLASSIFIER_HEURISTIC_FALLBACK_CODE]: CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE" in text


@pytest.mark.parametrize(
    "filename",
    ("paper-detail-classify-fallback.json", "paper-status-classify-fallback.json"),
)
def test_classify_fallback_fixtures_use_frozen_machine_code_only(filename: str) -> None:
    payload = json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))
    warnings = payload["data"]["classify_warnings"]
    assert warnings == [FROZEN_CODE]
    assert FROZEN_MESSAGE not in warnings
    assert FROZEN_MESSAGE not in json.dumps(payload["data"], ensure_ascii=False)
