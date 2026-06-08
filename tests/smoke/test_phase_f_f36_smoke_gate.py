"""F.6 smoke gate: T11文案、T12脚本、T13 mock 流水线、F.3 Prompt 文件."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.smoke
def test_t11_extract_heuristic_fallback_message_frozen() -> None:
    from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_MESSAGE

    assert EXTRACT_HEURISTIC_FALLBACK_MESSAGE == "触发启发式Fallback!"


@pytest.mark.smoke
def test_t12_run_extract_script_on_disk() -> None:
    assert (REPO_ROOT / "scripts" / "run_extract.py").is_file()


@pytest.mark.smoke
def test_t13_pipeline_mock_module_importable() -> None:
    spec = importlib.util.find_spec("tests.integration.test_pipeline_mock")
    assert spec is not None


@pytest.mark.smoke
def test_f36_extract_prompts_have_f3_sections() -> None:
    hss = (REPO_ROOT / "backend" / "prompts" / "extract_hss.md").read_text(encoding="utf-8")
    stem = (REPO_ROOT / "backend" / "prompts" / "extract_stem.md").read_text(encoding="utf-8")
    assert "F.3 Operational node definitions" in hss
    assert "F.3 Operational node definitions" in stem
    assert "Forbidden node types" in hss
    assert "Forbidden node types" in stem


@pytest.mark.smoke
def test_f36_forbidden_cross_paradigm_types_documented() -> None:
    hss = (REPO_ROOT / "backend" / "prompts" / "extract_hss.md").read_text(encoding="utf-8")
    stem = (REPO_ROOT / "backend" / "prompts" / "extract_stem.md").read_text(encoding="utf-8")
    for stem_type in ("Metric", "Baseline", "Dataset"):
        assert stem_type in hss
    for hss_type in ("AnalyticalLens", "IntellectualContext", "ObjectOrData"):
        assert hss_type in stem
