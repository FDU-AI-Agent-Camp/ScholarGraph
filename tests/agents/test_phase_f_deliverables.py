"""Phase F deliverables checklist (progress.md §10).

Static / schema regression for LLM extract + heuristic fallback.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from backend.agents.extract_constants import (
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.agents.extract_types import ExtractResult
from backend.config import Settings
from backend.schemas.paper import PaperStatusData

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
AGENTS_DIR = REPO_ROOT / "backend" / "agents"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def test_phase_f_x13_paper_status_data_exposes_extract_warnings() -> None:
    status = PaperStatusData.model_validate(
        {
            "paper_id": "f-x13",
            "status": "ready",
            "percent": 100,
            "stage": "ready",
            "message": "建图完成",
            "updated_at": "2026-06-07T00:00:00Z",
            "extract_warnings": [EXTRACT_HEURISTIC_FALLBACK_CODE],
        },
    )
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


def test_phase_f_x14_fallback_warning_code_frozen() -> None:
    assert EXTRACT_HEURISTIC_FALLBACK_CODE == "extract_heuristic_fallback"
    assert EXTRACT_HEURISTIC_FALLBACK_MESSAGE == "触发启发式Fallback!"


def test_phase_f_x20_openapi_status_documents_extract_warnings() -> None:
    text = OPENAPI.read_text(encoding="utf-8")
    assert "extract_warnings:" in text
    assert "extract_heuristic_fallback" in text


def test_phase_f_modules_exist() -> None:
    assert (AGENTS_DIR / "extract_llm.py").is_file()
    assert (AGENTS_DIR / "extract_heuristic.py").is_file()
    assert (AGENTS_DIR / "extract_types.py").is_file()
    assert (AGENTS_DIR / "extract_constants.py").is_file()


def test_phase_f_env_example_documents_extract_settings() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "EXTRACT_LLM_ENABLED" in text
    assert "EXTRACT_MAX_INPUT_CHARS" in text
    assert "EXTRACT_HEURISTIC_FALLBACK" in text


def test_phase_f_settings_defaults_enable_llm_and_fallback() -> None:
    settings = Settings(_env_file=None)
    assert settings.extract_llm_enabled is True
    assert settings.extract_heuristic_fallback is True
    assert settings.extract_max_input_chars == 20_000


def test_phase_f_extract_result_dataclass() -> None:
    from backend.schemas.graph import GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    graph = UnifiedPaperGraph(
        paper_id="p1",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="t", type="Thesis")],
        edges=[],
    )
    result = ExtractResult(graph=graph, warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE])
    assert result.warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


def test_phase_f_extractor_live_path_calls_extract_with_llm() -> None:
    from backend.agents import extractor

    source = inspect.getsource(extractor._extract_live)
    assert "extract_with_llm" in source
    assert "build_heuristic_graph" in source
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in inspect.getsource(extractor)


def test_phase_f_f21_load_extract_prompt_exported() -> None:
    from backend.agents.extract_llm import load_extract_prompt
    from backend.schemas.paradigm import Paradigm

    assert "Thesis" in load_extract_prompt(Paradigm.HSS)


def test_phase_f_f21_head_store_fallback_in_extractor() -> None:
    from backend.agents import extractor

    source = inspect.getsource(extractor._resolve_head_context)
    assert "HeadStore" in source


def test_phase_f_f21_truncation_log_in_extract_llm() -> None:
    from backend.agents import extract_llm

    assert "extract_input_truncated" in inspect.getsource(extract_llm.extract_with_llm)
