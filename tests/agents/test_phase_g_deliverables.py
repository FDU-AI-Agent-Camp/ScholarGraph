"""Phase G deliverables checklist (progress.md §12).

Static / schema regression for LLM classify + heuristic fallback.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.agents.classifier_types import ClassifyResult
from backend.config import Settings
from backend.schemas.paper import PaperStatusData

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
AGENTS_DIR = REPO_ROOT / "backend" / "agents"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def test_phase_g_paper_detail_exposes_classify_warnings() -> None:
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus

    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="g-x17",
        title="t",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        classify_warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    )
    assert detail.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_phase_g_paper_status_data_exposes_classify_warnings() -> None:
    status = PaperStatusData.model_validate(
        {
            "paper_id": "g-x13",
            "status": "ready",
            "percent": 100,
            "stage": "ready",
            "message": "建图完成",
            "updated_at": "2026-06-07T00:00:00Z",
            "classify_warnings": [CLASSIFIER_HEURISTIC_FALLBACK_CODE],
        },
    )
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_phase_g_fallback_warning_code_frozen() -> None:
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE == "classifier_heuristic_fallback"
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE == "触发分类启发式Fallback!"


def test_phase_g_openapi_documents_classify_warnings() -> None:
    text = OPENAPI.read_text(encoding="utf-8")
    assert "classify_warnings:" in text
    assert "PaperDetail:" in text


def test_phase_g_modules_exist() -> None:
    assert (AGENTS_DIR / "classifier_llm.py").is_file()
    assert (AGENTS_DIR / "classifier_heuristic.py").is_file()
    assert (AGENTS_DIR / "classifier_types.py").is_file()
    assert (AGENTS_DIR / "classifier_constants.py").is_file()


def test_phase_g_env_example_documents_classifier_settings() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "CLASSIFIER_LLM_ENABLED" in text
    assert "CLASSIFIER_HEURISTIC_FALLBACK" in text


def test_phase_g_settings_defaults_enable_llm_and_fallback() -> None:
    settings = Settings(_env_file=None)
    assert settings.classifier_llm_enabled is True
    assert settings.classifier_heuristic_fallback is True


def test_phase_g_classify_result_dataclass() -> None:
    from backend.schemas.paradigm import Paradigm, ParadigmClassification

    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="test",
    )
    result = ClassifyResult(classification=classification, warnings=[CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    assert result.warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


def test_phase_g_classifier_live_path_calls_classify_with_llm() -> None:
    from backend.agents import classifier

    live_source = inspect.getsource(classifier._classify_live)
    assert "classify_with_llm" in live_source
    assert "_fallback_to_heuristic" in live_source
    assert "CLASSIFIER_HEURISTIC_FALLBACK_CODE" in inspect.getsource(classifier._fallback_to_heuristic)


def test_phase_g_load_classifier_prompt_exported() -> None:
    from backend.agents.classifier_llm import load_classifier_prompt

    assert "paradigm" in load_classifier_prompt().lower()


def test_phase_g_fallback_helper_logs_classify_llm_fallback() -> None:
    from backend.agents import classifier

    source = inspect.getsource(classifier._fallback_to_heuristic)
    assert "classify_llm_fallback" in source
    assert "classify_heuristic" in source
