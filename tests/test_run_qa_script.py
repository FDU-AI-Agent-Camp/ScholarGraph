"""CLI tests for scripts/run_qa.py — M2 smoke, boundaries, red-path exit codes."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

RUN_QA_SCRIPT = REPO_ROOT / "scripts" / "run_qa.py"
_SUBPROCESS_TEXT_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}


@pytest.fixture(autouse=True)
def _restore_graph_data_dir_after_qa_cli() -> None:
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    original = os.environ.get("GRAPH_DATA_DIR")
    yield
    if original is None:
        os.environ.pop("GRAPH_DATA_DIR", None)
    else:
        os.environ["GRAPH_DATA_DIR"] = original
    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.fixture
def run_qa_module():
    spec = importlib.util.spec_from_file_location("run_qa", RUN_QA_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_qa"] = module
    spec.loader.exec_module(module)
    return module


def test_run_qa_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_QA_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 0
    assert "--smoke-m2" in result.stdout


def test_run_qa_usage_error_without_args(run_qa_module) -> None:
    code = run_qa_module.main([])
    assert code == run_qa_module.EXIT_USAGE_ERROR


@pytest.mark.asyncio
async def test_run_qa_single_turn_verifies_citation(run_qa_module, tmp_path: Path) -> None:
    mod = run_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    mod.seed_m2_qa_graph(graph_dir)

    code = await mod.main_async(
        mod.parse_args(["hss-001", "这篇论文做了什么？", "--graph-dir", str(graph_dir)]),
    )
    assert code == mod.EXIT_SUCCESS


@pytest.mark.asyncio
async def test_run_qa_fails_when_graph_missing(run_qa_module, tmp_path: Path) -> None:
    mod = run_qa_module
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    code = await mod.main_async(
        mod.parse_args(["hss-001", "问题？", "--graph-dir", str(empty_dir)]),
    )
    assert code == mod.EXIT_QA_FAILED


@pytest.mark.asyncio
async def test_run_qa_smoke_m2_requires_seed_or_existing_graph(run_qa_module, tmp_path: Path) -> None:
    mod = run_qa_module
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    code = await mod.main_async(mod.parse_args(["--smoke-m2", "--graph-dir", str(empty_dir)]))
    assert code == mod.EXIT_QA_FAILED


def test_bind_graph_dir_updates_settings(run_qa_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.config import get_settings

    mod = run_qa_module
    target = tmp_path / "bound-graphs"
    target.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path / "other"))
    get_settings.cache_clear()

    mod.bind_graph_dir(target)

    assert Path(get_settings().graph_data_dir).resolve() == target.resolve()


@pytest.mark.asyncio
async def test_run_qa_red_missing_citation_events(run_qa_module, tmp_path: Path) -> None:
    """Red: Mock 无 citation 时 verify_citation 失败."""
    mod = run_qa_module
    graph_dir = tmp_path / "graphs"
    mod.seed_m2_qa_graph(graph_dir)

    result = mod.QaRunResult(answer_text="无引用", citations=[], error_code=None)
    assert mod.verify_citation(result, graph_dir, "hss-001") is False


def test_run_qa_subprocess_smoke_with_seed(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    env = {
        **os.environ,
        "LLM_MODE": "mock",
        "GRAPH_DATA_DIR": str(graph_dir),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, str(RUN_QA_SCRIPT), "--smoke-m2", "--seed-demo-graph", "--graph-dir", str(graph_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env=env,
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "citation" in result.stdout.lower() or "✓ citation" in result.stdout
