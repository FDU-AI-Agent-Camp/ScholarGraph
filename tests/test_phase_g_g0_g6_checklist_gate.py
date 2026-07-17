# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase G G.0–G.6 checklist gate (unit + special regression).

Maps progress.md §11 / §12 deliverables to automated assertions.
Default CI (non-red).
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from backend.agents.classifier import classify
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.config import Settings, get_settings
from backend.graph import nodes as graph_nodes
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paradigm import Paradigm, ParadigmClassification

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
FIXTURES_DIR = REPO_ROOT / "docs" / "api" / "fixtures"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
FE_CLASSIFY_WARNINGS = REPO_ROOT / "frontend" / "src" / "utils" / "classifyWarnings.ts"
GENERATED_SCHEMA = REPO_ROOT / "frontend" / "src" / "api" / "generated" / "schema.d.ts"

STEM_SAMPLE = (
    "Title: Agent framework benchmark. We evaluate the model on datasets with accuracy, "
    "F1 metrics, baselines, and ablation experiments."
)


@pytest.fixture
def live_classify_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "true")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "true")
    get_settings.cache_clear()
    reset_llm_client_cache()


G0_TEST_FILES = (
    "tests/agents/test_classify_g4_llm_mode_gate.py",
    "tests/test_llm_mode_global_gate.py",
)
G1_TEST_FILES = (
    "tests/agents/test_classifier_llm.py",
    "tests/agents/test_classifier_heuristic.py",
    "tests/agents/test_phase_g_unit_gate.py",
)
G2_TEST_FILES = (
    "tests/services/test_paper_status_classify_warnings.py",
    "tests/integration/test_phase_g_classify_pipeline.py",
    "tests/schemas/test_paper_g28_contract.py",
)
G3_FE_TEST_FILES = (
    "frontend/src/utils/classifyWarnings.test.ts",
    "frontend/src/components/papers/PaperStatusPanel.spec.ts",
    "frontend/src/views/PaperDetailView.spec.ts",
)
G5_TEST_FILES = (
    "tests/eval/test_m0_classifier_gold.py",
    "tests/smoke/test_phase_g_smoke.py",
    "tests/integration/test_phase_g_fe_be_integration.py",
)


def _openapi_schema_properties(spec: dict, schema_name: str) -> dict:
    """Resolve properties for direct or allOf-composed OpenAPI schemas."""
    schema = spec["components"]["schemas"][schema_name]
    if "properties" in schema:
        return schema["properties"]
    merged: dict = {}
    for item in schema.get("allOf", ()):
        if "properties" in item:
            merged.update(item["properties"])
    return merged


def test_g0_product_decision_files_exist() -> None:
    for rel in G0_TEST_FILES:
        assert (REPO_ROOT / rel).is_file(), rel


@pytest.mark.asyncio
async def test_g0_live_llm_success_does_not_call_heuristic(live_classify_env: None) -> None:
    """G.0: heuristic is fallback-only — live LLM success must not invoke classify_heuristic."""
    _ = live_classify_env
    expected = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.92,
        reason="Quantitative benchmark.",
    )

    with (
        patch(
            "backend.agents.classifier.classify_with_llm",
            new=AsyncMock(return_value=expected),
        ),
        patch("backend.agents.classifier.classify_heuristic") as heuristic_mock,
    ):
        result = await classify(STEM_SAMPLE)

    assert result.warnings == []
    heuristic_mock.assert_not_called()


def test_g0_classify_node_only_consumes_classifier_input() -> None:
    """G.0: ingest / head refine assembly unchanged — classify_node reads classifier_input only."""
    source = inspect.getsource(graph_nodes.classify_node)
    assert 'state["classifier_input"]' in source
    assert "head_merge" not in source
    assert "ingest_pdf" not in source


def test_g0_paradigm_enum_is_stem_or_hss_only() -> None:
    assert set(Paradigm) == {Paradigm.STEM, Paradigm.HSS}


def test_g1_module_split_aligned_with_phase_f() -> None:
    agents = REPO_ROOT / "backend" / "agents"
    for name in (
        "classifier.py",
        "classifier_llm.py",
        "classifier_heuristic.py",
        "classifier_constants.py",
        "classifier_types.py",
    ):
        assert (agents / name).is_file(), name

    llm_source = inspect.getsource(importlib.import_module("backend.agents.classifier_llm"))
    heuristic_source = inspect.getsource(importlib.import_module("backend.agents.classifier_heuristic"))
    orchestrator = inspect.getsource(importlib.import_module("backend.agents.classifier"))

    assert "classify_with_llm" in llm_source
    assert "def classify_heuristic" in heuristic_source
    assert "classify_with_llm" in orchestrator
    assert "classify_heuristic" in orchestrator
    assert "mock_classify" in orchestrator


def test_g1_test_files_exist() -> None:
    for rel in G1_TEST_FILES:
        assert (REPO_ROOT / rel).is_file(), rel


def test_g2_classify_warnings_on_status_and_detail_schemas() -> None:
    from backend.schemas.paper import PaperDetail, PaperStatusData

    assert "classify_warnings" in PaperStatusData.model_fields
    assert "classify_warnings" in PaperDetail.model_fields


def test_g2_test_files_exist() -> None:
    for rel in G2_TEST_FILES:
        assert (REPO_ROOT / rel).is_file(), rel


def test_g3_frontend_test_files_exist() -> None:
    for rel in G3_FE_TEST_FILES:
        assert (REPO_ROOT / rel).is_file(), rel


def test_g3_fe_be_constants_match_backend() -> None:
    from backend.agents.classifier_constants import (
        CLASSIFIER_HEURISTIC_FALLBACK_CODE,
        CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
    )

    text = FE_CLASSIFY_WARNINGS.read_text(encoding="utf-8")
    fe_code = re.search(r"CLASSIFIER_HEURISTIC_FALLBACK_CODE = '([^']+)'", text)
    fe_message = re.search(r"CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE = '([^']+)'", text)
    assert fe_code is not None
    assert fe_message is not None
    assert fe_code.group(1) == CLASSIFIER_HEURISTIC_FALLBACK_CODE
    assert fe_message.group(1) == CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE


def test_g4_env_example_documents_classifier_switches() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "CLASSIFIER_LLM_ENABLED=true" in text
    assert "CLASSIFIER_HEURISTIC_FALLBACK=true" in text
    assert "classify_warnings" in text


def test_g4_settings_parse_classifier_env_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    monkeypatch.setenv("CLASSIFIER_HEURISTIC_FALLBACK", "false")
    settings = Settings(_env_file=None)
    assert settings.classifier_llm_enabled is False
    assert settings.classifier_heuristic_fallback is False


@pytest.mark.asyncio
async def test_g4_mock_mode_wins_over_classifier_llm_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("CLASSIFIER_LLM_ENABLED", "false")
    get_settings.cache_clear()
    reset_llm_client_cache()

    with patch("backend.agents.classifier.classify_with_llm", new=AsyncMock()) as llm_mock:
        result = await classify(STEM_SAMPLE)

    llm_mock.assert_not_awaited()
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE not in result.warnings


def test_g5_phase_g_test_matrix_files_exist() -> None:
    for rel in G5_TEST_FILES:
        assert (REPO_ROOT / rel).is_file(), rel


def test_g6_openapi_classify_warnings_on_status_and_detail() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))

    for schema_name in ("PaperStatusData", "PaperDetail"):
        props = _openapi_schema_properties(spec, schema_name)
        assert "classify_warnings" in props
        assert props["classify_warnings"]["type"] == "array"
        assert props["classify_warnings"]["items"]["type"] == "string"


def test_g6_classify_fallback_fixtures_validate_and_use_machine_code() -> None:
    for name in ("paper-status-classify-fallback.json", "paper-detail-classify-fallback.json"):
        payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        warnings = payload["data"]["classify_warnings"]
        assert warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_g6_generated_typescript_schema_includes_classify_warnings() -> None:
    text = GENERATED_SCHEMA.read_text(encoding="utf-8")
    assert "classify_warnings" in text


def test_g6_paradigm_classification_openapi_unchanged_without_warnings_field() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    paradigm = spec["components"]["schemas"]["ParadigmClassification"]
    assert set(paradigm["properties"].keys()) == {"paradigm", "confidence", "reason"}
    assert "classify_warnings" not in paradigm["properties"]
