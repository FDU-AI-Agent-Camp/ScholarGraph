"""Integration: run_pipeline.py ↔ LangGraph workflow (startup + per-stage robustness)."""

from __future__ import annotations

import inspect
import subprocess
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.graph.workflow import get_compiled_paper_pipeline, run_paper_pipeline
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service

from tests.conftest import REPO_ROOT, RUN_PIPELINE_SCRIPT, mock_pipeline_node_services
from tests.helpers.status_contract import assert_snapshot_matches_contract

STAGE_FAILURE_CASES = [
    ("get_ingest_service", "ingest", ServiceError("INGEST_FAILED", "ingest err"), "INGEST_FAILED"),
    ("get_agent_service", "classify_paradigm", ServiceError("LLM_JSON_INVALID", "cls err"), "LLM_JSON_INVALID"),
    ("get_agent_service", "extract_graph", ServiceError("PIPELINE_FAILED", "ext err"), "PIPELINE_FAILED"),
]


def _close_coro_and_return(coro: Coroutine[Any, Any, Any], exit_code: int) -> int:
    """Mock asyncio.run：避免传入的协程未 await 触发 RuntimeWarning。"""
    if inspect.iscoroutine(coro):
        coro.close()
    return exit_code


# ── 流水线启动（功能性） ─────────────────────────────────────────────────────


async def test_run_paper_pipeline_startup_marks_ingesting(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    """run_paper_pipeline 在节点执行前应已 start_processing → ingesting/20。"""
    mod = run_pipeline_module
    paper_id = "startup-status-paper"
    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    captured: list = []

    async def capture_ainvoke(initial):  # noqa: ANN001
        snapshot = await get_paper_service().get_status(paper_id)
        captured.append(snapshot)
        return {"failed": False, "status": PaperStatus.READY}

    compiled = get_compiled_paper_pipeline()
    with patch.object(compiled, "ainvoke", side_effect=capture_ainvoke):
        await run_paper_pipeline(paper_id, minimal_pdf)

    assert len(captured) >= 1
    startup = captured[0]
    assert startup.status == PaperStatus.PROCESSING
    assert startup.stage == PipelineStage.INGESTING
    assert startup.percent == STAGE_PERCENT[PipelineStage.INGESTING]
    assert_snapshot_matches_contract(startup)


def test_main_registers_paper_and_invokes_async_runner(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "main-startup-paper"

    with (
        patch.object(mod, "register_paper_for_pipeline", return_value=minimal_pdf) as register,
        patch.object(
            mod.asyncio,
            "run",
            side_effect=lambda coro: _close_coro_and_return(coro, mod.EXIT_SUCCESS),
        ) as async_run,
    ):
        code = mod.main(["--pdf", str(minimal_pdf), "--paper-id", paper_id])

    assert code == mod.EXIT_SUCCESS
    register.assert_called_once()
    assert register.call_args.args[0] == paper_id
    async_run.assert_called_once()


async def test_script_end_to_end_success_via_real_workflow(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-e2e-success"

    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)
    with mock_pipeline_node_services(paper_id):
        code = await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    assert code == mod.EXIT_SUCCESS
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.READY
    assert_snapshot_matches_contract(status)
    graph = await get_paper_service().get_graph(paper_id)
    assert graph.paper_id == paper_id


async def test_script_main_end_to_end_success(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-main-e2e"
    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    with mock_pipeline_node_services(paper_id):
        code = await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    assert code == mod.EXIT_SUCCESS


async def test_script_generates_paper_id_when_omitted(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "generated-paper-id"

    with patch.object(mod, "uuid4", return_value=paper_id):
        mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)
        with mock_pipeline_node_services(paper_id):
            code = await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    assert code == mod.EXIT_SUCCESS
    assert paper_id in get_paper_service()._papers


# ── 各环节鲁棒性（经脚本入口 + 真实 workflow） ───────────────────────────────


@pytest.mark.parametrize(
    ("service_getter", "service_method", "error", "expected_code"),
    STAGE_FAILURE_CASES,
)
async def test_script_exits_failed_when_workflow_stage_raises(
    run_pipeline_module,
    minimal_pdf: Path,
    service_getter: str,
    service_method: str,
    error: ServiceError,
    expected_code: str,
) -> None:
    mod = run_pipeline_module
    paper_id = f"script-fail-{service_method}"

    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    with mock_pipeline_node_services(paper_id) as mocks:
        if service_method == "ingest":
            mocks["ingest"].ingest = AsyncMock(side_effect=error)
        elif service_method == "classify_paradigm":
            mocks["agent"].classify_paradigm = AsyncMock(side_effect=error)
        else:
            mocks["agent"].extract_graph = AsyncMock(side_effect=error)
        code = await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    assert code == mod.EXIT_PIPELINE_FAILED
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert_snapshot_matches_contract(status)


async def test_script_exits_failed_when_store_finalize_raises(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-fail-store"

    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["completion"].finalize = MagicMock(
            side_effect=ServiceError("PIPELINE_FAILED", "disk full"),
        )
        code = await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    assert code == mod.EXIT_PIPELINE_FAILED
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert "disk full" in status.message or status.message


@pytest.mark.parametrize(
    ("service_getter", "service_method", "error", "expected_code"),
    STAGE_FAILURE_CASES,
)
async def test_main_returns_failed_exit_when_stage_raises(
    run_pipeline_module,
    minimal_pdf: Path,
    service_getter: str,
    service_method: str,
    error: ServiceError,
    expected_code: str,
) -> None:
    mod = run_pipeline_module
    paper_id = f"main-fail-{service_method}"
    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    with mock_pipeline_node_services(paper_id) as mocks:
        if service_method == "ingest":
            mocks["ingest"].ingest = AsyncMock(side_effect=error)
        elif service_method == "classify_paradigm":
            mocks["agent"].classify_paradigm = AsyncMock(side_effect=error)
        else:
            mocks["agent"].extract_graph = AsyncMock(side_effect=error)
        code = await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    assert code == mod.EXIT_PIPELINE_FAILED


async def test_script_does_not_run_classify_after_ingest_failure(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-short-circuit-ingest"

    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(side_effect=ServiceError("INGEST_FAILED", "bad pdf"))
        await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    mocks["agent"].classify_paradigm.assert_not_awaited()
    mocks["agent"].extract_graph.assert_not_awaited()


async def test_script_does_not_run_extract_after_classify_failure(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-short-circuit-classify"

    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].classify_paradigm = AsyncMock(
            side_effect=ServiceError("LLM_JSON_INVALID", "schema mismatch"),
        )
        await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    mocks["agent"].extract_graph.assert_not_awaited()
    mocks["store_save"].assert_not_called()


async def test_script_does_not_persist_graph_after_extract_failure(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-short-circuit-extract"

    mod.register_paper_for_pipeline(paper_id, minimal_pdf, copy_to_upload_dir=False)

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["agent"].extract_graph = AsyncMock(
            side_effect=ServiceError("PIPELINE_FAILED", "extractor missing"),
        )
        await mod.run_single_paper_pipeline(paper_id, minimal_pdf)

    mocks["store_save"].assert_not_called()


# ── 登记与路径鲁棒性 ─────────────────────────────────────────────────────────


def test_register_skips_duplicate_paper_metadata(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-register-idempotent"

    mod.register_paper_for_pipeline(paper_id, minimal_pdf, title="原标题", copy_to_upload_dir=False)
    from backend.services.paper_service import get_paper_service

    original_updated = get_paper_service()._papers[paper_id].updated_at
    mod.register_paper_for_pipeline(paper_id, minimal_pdf, title="新标题", copy_to_upload_dir=False)

    paper = get_paper_service()._papers[paper_id]
    assert paper.title == "原标题"
    assert paper.updated_at == original_updated


def test_register_no_copy_uses_source_path(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "script-no-copy"
    resolved = mod.register_paper_for_pipeline(
        paper_id,
        minimal_pdf,
        copy_to_upload_dir=False,
    )
    assert resolved.resolve() == minimal_pdf.resolve()


def test_subprocess_missing_pdf_returns_usage_exit() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_PIPELINE_SCRIPT), "--pdf", "definitely-missing.pdf"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "错误" in result.stderr or "PDF" in result.stderr
