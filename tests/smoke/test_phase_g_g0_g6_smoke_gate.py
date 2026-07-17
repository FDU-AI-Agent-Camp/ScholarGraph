# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase G G.0–G.6 smoke gate: deliverables exist and key contracts hold."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.smoke
def test_smoke_g0_g6_checklist_gate_module_on_disk() -> None:
    assert (REPO_ROOT / "tests" / "test_phase_g_g0_g6_checklist_gate.py").is_file()


@pytest.mark.smoke
def test_smoke_g0_g6_red_module_on_disk() -> None:
    assert (REPO_ROOT / "tests" / "test_phase_g_g0_g6_red.py").is_file()


@pytest.mark.smoke
def test_smoke_g6_openapi_api_gate_module_on_disk() -> None:
    assert (REPO_ROOT / "tests" / "api" / "test_phase_g_g6_openapi_gate.py").is_file()


@pytest.mark.smoke
def test_smoke_g3_frontend_g0_g6_red_test_on_disk() -> None:
    assert (REPO_ROOT / "frontend" / "src" / "test" / "phase-g-g0-g6-red.test.ts").is_file()


@pytest.mark.smoke
def test_smoke_g6_frontend_openapi_fixtures_test_on_disk() -> None:
    assert (REPO_ROOT / "frontend" / "src" / "test" / "phase-g-g6-openapi-fixtures.test.ts").is_file()


@pytest.mark.smoke
def test_smoke_g0_classifier_prompt_referenced_by_llm_module() -> None:
    spec = importlib.util.find_spec("backend.agents.classifier_llm")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.CLASSIFIER_PROMPT_PATH.is_file()


@pytest.mark.smoke
def test_smoke_g2_classify_fallback_fixtures_on_disk() -> None:
    fixtures = REPO_ROOT / "docs" / "api" / "fixtures"
    assert (fixtures / "paper-status-classify-fallback.json").is_file()
    assert (fixtures / "paper-detail-classify-fallback.json").is_file()


@pytest.mark.smoke
def test_smoke_g4_env_example_phase_g_section() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "Phase G" in text or "范式分类" in text
    assert "CLASSIFIER_LLM_ENABLED" in text
    assert "CLASSIFIER_HEURISTIC_FALLBACK" in text
