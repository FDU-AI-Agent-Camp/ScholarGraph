# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""G.4 smoke gate: LLM_MODE env + classifier switches + mock path wiring."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from backend.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


@pytest.mark.smoke
def test_smoke_g4_env_example_classifier_section() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "CLASSIFIER_LLM_ENABLED=true" in text
    assert "CLASSIFIER_HEURISTIC_FALLBACK=true" in text
    assert "范式分类（Phase G）" in text


@pytest.mark.smoke
def test_smoke_g4_classifier_checks_is_llm_mock_before_live_path() -> None:
    from backend.agents import classifier

    source = inspect.getsource(classifier.classify)
    assert "is_llm_mock" in source
    assert "mock_classify" in source
    assert source.index("is_llm_mock") < source.index("_classify_live")


@pytest.mark.smoke
def test_smoke_g4_settings_default_classifier_llm_and_fallback_enabled() -> None:
    settings = Settings(_env_file=None)
    assert settings.classifier_llm_enabled is True
    assert settings.classifier_heuristic_fallback is True
    assert settings.llm_mode == "mock"


@pytest.mark.smoke
def test_smoke_g4_head_merge_skips_llm_in_mock_mode() -> None:
    from backend.ingest import head_merge

    source = inspect.getsource(head_merge.merge_head_candidates)
    assert "is_llm_mock" in source
