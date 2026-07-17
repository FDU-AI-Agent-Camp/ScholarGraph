# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

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


def test_phase_f_x17_paper_detail_exposes_extract_warnings() -> None:
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus

    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="f-x17",
        title="t",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        extract_warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
    )
    assert detail.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


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
    assert "PaperDetail:" in text


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


def test_phase_f_extractor_live_path_has_extraction_paths() -> None:
    from backend.agents import extractor

    live_source = inspect.getsource(extractor._extract_live)
    assert "_extract_single_phase" in live_source
    assert "_extract_two_phase" in live_source
    assert "_fallback_to_heuristic" in live_source

    single_phase_source = inspect.getsource(extractor._extract_single_phase)
    assert "extract_with_llm" in single_phase_source
    assert "EXTRACT_HEURISTIC_FALLBACK_CODE" in inspect.getsource(extractor._fallback_to_heuristic)


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


def test_phase_f_f22_fallback_helper_and_log() -> None:
    from backend.agents import extractor

    source = inspect.getsource(extractor._fallback_to_heuristic)
    assert "extract_llm_fallback" in source
    assert "build_heuristic_graph" in source
    assert "EXTRACT_HEURISTIC_FALLBACK_CODE" in source


def test_phase_f_f22_heuristic_legacy_aliases() -> None:
    from backend.agents import extract_heuristic

    assert extract_heuristic._build_hss_graph is extract_heuristic.build_hss_graph
    assert extract_heuristic._build_stem_graph is extract_heuristic.build_stem_graph


def test_phase_f_f22_validate_llm_graph_rejects_empty_edges() -> None:
    from backend.agents.extract_llm import _validate_llm_graph
    from backend.schemas.graph import GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm

    graph = UnifiedPaperGraph(
        paper_id="p",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="t", type="Thesis")],
        edges=[],
    )
    try:
        _validate_llm_graph(graph, expected_paradigm=Paradigm.HSS)
        raised = False
    except ValueError as exc:
        raised = True
        assert "no edges" in str(exc)
    assert raised
