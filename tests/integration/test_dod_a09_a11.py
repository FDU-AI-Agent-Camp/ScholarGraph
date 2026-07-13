"""V1 DoD A-09 / A-11 — M2 QA smoke CLI + M4 pipeline mock E2E."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service, reset_persistence_singletons

from tests.conftest import REPO_ROOT, RUN_PIPELINE_SCRIPT
from tests.ingest.conftest import write_text_pdf

RUN_QA_SCRIPT = REPO_ROOT / "scripts" / "run_qa.py"
_SUBPROCESS_TEXT_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}


def _load_run_qa_module():
    spec = importlib.util.spec_from_file_location("run_qa", RUN_QA_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pipeline_mock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    graph_dir = tmp_path / "graphs"
    upload_dir.mkdir()
    graph_dir.mkdir()
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    reset_persistence_singletons()
    reset_llm_client_cache()
    return tmp_path


def test_a09_run_qa_smoke_m2_subprocess_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    env = {
        **os.environ,
        "LLM_MODE": "mock",
        "GRAPH_DATA_DIR": str(graph_dir),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, str(RUN_QA_SCRIPT), "--smoke-m2", "--seed-demo-graph"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env=env,
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "M2 smoke" in result.stdout
    assert "verification" in result.stdout or "验证" in result.stdout


@pytest.mark.asyncio
async def test_a11_pipeline_mock_e2e_reaches_ready(
    pipeline_mock_env: Path,
    run_pipeline_module,
) -> None:
    """A-11 / M4: ingest → classify → extract → store with LLM_MODE=mock."""
    mod = run_pipeline_module
    paper_id = "a11-mock-pipeline"
    pdf_path = write_text_pdf(
        pipeline_mock_env / "hss-demo.pdf",
        "\n".join(
            [
                "再探夏尔巴人父系历史",
                "Abstract",
                "本文从分子考古视角考察夏尔巴人父系源流。",
                "Keywords",
                "夏尔巴, 父系, 民族史",
                "Introduction",
                "夏尔巴人是生活于我国和尼泊尔交界地区的少数民族。",
            ],
        ),
    )
    mod.register_paper_for_pipeline(paper_id, pdf_path, copy_to_upload_dir=False)
    code = await mod.run_single_paper_pipeline(paper_id, pdf_path)

    assert code == mod.EXIT_SUCCESS
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    graph = await get_paper_service().get_graph(paper_id)
    assert graph.paper_id == paper_id
    assert graph.nodes


def test_a11_run_pipeline_subprocess_exits_zero(pipeline_mock_env: Path) -> None:
    mod_spec = importlib.util.spec_from_file_location("run_pipeline", RUN_PIPELINE_SCRIPT)
    assert mod_spec is not None and mod_spec.loader is not None
    run_pipeline = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(run_pipeline)

    paper_id = "a11-cli-pipeline"
    pdf_path = write_text_pdf(
        pipeline_mock_env / "cli-hss.pdf",
        "夏尔巴人父系历史\nAbstract\n分子考古与民族史研究",
    )
    env = {
        **os.environ,
        "LLM_MODE": "mock",
        "UPLOAD_DIR": str(pipeline_mock_env / "uploads"),
        "GRAPH_DATA_DIR": str(pipeline_mock_env / "graphs"),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(RUN_PIPELINE_SCRIPT),
            "--pdf",
            str(pdf_path),
            "--paper-id",
            paper_id,
            "--no-copy",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env=env,
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "ready" in result.stdout.lower() or "建图完成" in result.stdout


def test_a11_run_pipeline_missing_pdf_exits_usage_error() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_PIPELINE_SCRIPT), "--pdf", "definitely-missing-m2.pdf"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 2
    assert "错误" in result.stderr or "PDF" in result.stderr


@pytest.mark.asyncio
async def test_a11_pipeline_live_mode_heuristic_be2_succeeds(
    run_pipeline_module,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM_MODE=live uses BE-2 heuristic classify/extract (no cloud LLM required)."""
    mod = run_pipeline_module
    monkeypatch.setenv("LLM_MODE", "live")
    get_settings.cache_clear()
    reset_llm_client_cache()
    get_paper_service.cache_clear()

    paper_id = "a11-live-heuristic"
    pdf_path = write_text_pdf(tmp_path / "live-heuristic.pdf", "夏尔巴人父系历史研究")
    mod.register_paper_for_pipeline(paper_id, pdf_path, copy_to_upload_dir=False)

    code = await mod.run_single_paper_pipeline(paper_id, pdf_path)
    assert code == mod.EXIT_SUCCESS

    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY


@pytest.mark.asyncio
async def test_a11_pipeline_mock_then_m2_qa_chain(
    pipeline_mock_env: Path,
    run_pipeline_module,
) -> None:
    """Functional chain: pipeline ready → qa_stream returns verifiable citation."""
    from backend.graph.qa import qa_stream
    from backend.graph.qa_samples import seed_m2_qa_graph

    mod = run_pipeline_module
    paper_id = "a11-qa-chain"
    pdf_path = write_text_pdf(
        pipeline_mock_env / "chain.pdf",
        "夏尔巴人父系历史\nAbstract\n分子考古视角",
    )
    mod.register_paper_for_pipeline(paper_id, pdf_path, copy_to_upload_dir=False)
    code = await mod.run_single_paper_pipeline(paper_id, pdf_path)
    assert code == mod.EXIT_SUCCESS

    graph = await get_paper_service().get_graph(paper_id)
    store_dir = Path(get_settings().graph_data_dir)
    seed_m2_qa_graph(store_dir, paper_id=paper_id)

    events: list[tuple[str, dict]] = []
    async for evt in qa_stream(paper_id, "这篇论文做了什么？"):
        events.append((evt.event, evt.data))

    citations = [payload for name, payload in events if name == "citation"]
    assert citations
    cite = citations[0]
    assert cite["paper_id"] == paper_id
    node_ids = {node.id for node in graph.nodes}
    assert cite["node_id"] in node_ids or cite["node_id"] == "n1"
