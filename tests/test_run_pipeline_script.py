# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for scripts/run_pipeline.py helpers and CLI surface."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage

from tests.conftest import RUN_PIPELINE_SCRIPT

REPO_ROOT = RUN_PIPELINE_SCRIPT.parents[1]
SCRIPT_PATH = RUN_PIPELINE_SCRIPT

_SUBPROCESS_TEXT_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}


def test_run_pipeline_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 0
    assert "--pdf" in result.stdout


def test_parse_args_requires_pdf(run_pipeline_module) -> None:
    with pytest.raises(SystemExit):
        run_pipeline_module.parse_args([])


def test_parse_args_reads_optional_fields(run_pipeline_module, minimal_pdf: Path) -> None:
    args = run_pipeline_module.parse_args(
        ["--pdf", str(minimal_pdf), "--paper-id", "p-1", "--title", "T", "--no-copy"],
    )
    assert args.pdf == minimal_pdf
    assert args.paper_id == "p-1"
    assert args.title == "T"
    assert args.no_copy is True


def test_format_status_line_includes_stage_and_percent(run_pipeline_module) -> None:
    line = run_pipeline_module._format_status_line(
        PaperStatusData(
            paper_id="x",
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="正在范式分类",
            updated_at=datetime.now(UTC),
        ),
    )
    assert "processing" in line
    assert "classifying" in line
    assert "50%" in line


def test_register_paper_for_pipeline_copies_pdf_and_sets_pending(
    run_pipeline_module,
    minimal_pdf: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "cli-test-paper"
    dest = mod.register_paper_for_pipeline(paper_id, minimal_pdf, title="CLI 测试")

    assert dest.is_file()
    from backend.services.paper_service import get_paper_service

    paper = get_paper_service()._papers[paper_id]
    assert paper.status.value == "pending"
    assert paper.title == "CLI 测试"


def test_main_returns_usage_exit_when_pdf_missing(run_pipeline_module, tmp_path: Path) -> None:
    mod = run_pipeline_module
    missing = tmp_path / "missing.pdf"
    code = mod.main(["--pdf", str(missing), "--paper-id", "orphan-cli"])
    assert code == mod.EXIT_USAGE_ERROR


async def test_run_single_paper_pipeline_success_exit(run_pipeline_module, tmp_path: Path) -> None:
    mod = run_pipeline_module
    paper_id = "cli-success-paper"
    pdf_path = tmp_path / "ok.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    from datetime import UTC, datetime

    from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage

    with patch.object(mod, "run_paper_pipeline", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"failed": False}
        with patch.object(mod, "get_paper_service") as mock_svc_factory:
            mock_svc = mock_svc_factory.return_value
            mock_svc.get_status = AsyncMock(
                return_value=PaperStatusData(
                    paper_id=paper_id,
                    status=PaperStatus.READY,
                    percent=100,
                    stage=PipelineStage.READY,
                    message="建图完成",
                    updated_at=datetime.now(UTC),
                ),
            )
            code = await mod.run_single_paper_pipeline(paper_id, pdf_path)

    assert code == mod.EXIT_SUCCESS


async def test_run_single_paper_pipeline_failed_exit(run_pipeline_module, tmp_path: Path) -> None:
    mod = run_pipeline_module
    paper_id = "cli-fail-paper"
    pdf_path = tmp_path / "fail.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with patch.object(mod, "run_paper_pipeline", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {
            "failed": True,
            "error_code": "INGEST_FAILED",
            "error_message": "无法解析",
        }
        with patch.object(mod, "get_paper_service") as mock_svc_factory:
            mock_svc = mock_svc_factory.return_value
            mock_svc.get_status = AsyncMock(
                return_value=PaperStatusData(
                    paper_id=paper_id,
                    status=PaperStatus.FAILED,
                    percent=0,
                    stage=PipelineStage.FAILED,
                    message="无法解析",
                    updated_at=datetime.now(UTC),
                ),
            )
            code = await mod.run_single_paper_pipeline(paper_id, pdf_path)

    assert code == mod.EXIT_PIPELINE_FAILED


async def test_run_single_paper_pipeline_warns_on_unexpected_terminal(
    run_pipeline_module,
    tmp_path: Path,
) -> None:
    mod = run_pipeline_module
    paper_id = "cli-stuck-processing"
    pdf_path = tmp_path / "stuck.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with patch.object(mod, "run_paper_pipeline", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"failed": False}
        with patch.object(mod, "get_paper_service") as mock_svc_factory:
            mock_svc = mock_svc_factory.return_value
            mock_svc.get_status = AsyncMock(
                return_value=PaperStatusData(
                    paper_id=paper_id,
                    status=PaperStatus.PROCESSING,
                    percent=50,
                    stage=PipelineStage.CLASSIFYING,
                    message="卡住",
                    updated_at=datetime.now(UTC),
                ),
            )
            code = await mod.run_single_paper_pipeline(paper_id, pdf_path)

    assert code == mod.EXIT_PIPELINE_FAILED
