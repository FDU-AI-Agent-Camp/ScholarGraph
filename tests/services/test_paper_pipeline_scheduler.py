"""Upload pipeline scheduling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.services import paper_pipeline_scheduler as scheduler_mod
from backend.services.paper_pipeline_scheduler import ensure_head_refine_scheduled, schedule_paper_pipeline


@pytest.fixture(autouse=True)
def _clear_head_refine_task_registry() -> None:
    scheduler_mod._head_refine_tasks.clear()
    yield
    scheduler_mod._head_refine_tasks.clear()


@pytest.mark.asyncio
async def test_ensure_head_refine_scheduled_starts_once_per_paper(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% mock")

    with patch(
        "backend.services.paper_pipeline_scheduler._refine_head_safe",
        new_callable=AsyncMock,
    ) as mock_refine:
        ensure_head_refine_scheduled("paper-dedup", pdf_path)
        ensure_head_refine_scheduled("paper-dedup", pdf_path)
        await asyncio.sleep(0)

    mock_refine.assert_awaited_once_with("paper-dedup", pdf_path.resolve())


@pytest.mark.asyncio
async def test_ensure_head_refine_scheduled_can_restart_after_done(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% mock")

    with patch(
        "backend.services.paper_pipeline_scheduler._refine_head_safe",
        new_callable=AsyncMock,
    ) as mock_refine:
        ensure_head_refine_scheduled("paper-restart", pdf_path)
        await asyncio.sleep(0)
        scheduler_mod._head_refine_tasks.clear()
        ensure_head_refine_scheduled("paper-restart", pdf_path)
        await asyncio.sleep(0)

    assert mock_refine.await_count == 2


@pytest.mark.asyncio
async def test_schedule_paper_pipeline_invokes_run_paper_pipeline(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with (
        patch(
            "backend.services.paper_pipeline_scheduler._refine_head_safe",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.graph.workflow.run_paper_pipeline",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        task = schedule_paper_pipeline("paper-1", pdf_path)
        await task
        await asyncio.sleep(0)

    mock_run.assert_awaited_once_with("paper-1", pdf_path.resolve())


@pytest.mark.asyncio
async def test_schedule_paper_pipeline_starts_head_refine(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with (
        patch(
            "backend.services.paper_pipeline_scheduler._refine_head_safe",
            new_callable=AsyncMock,
        ) as mock_refine,
        patch(
            "backend.graph.workflow.run_paper_pipeline",
            new_callable=AsyncMock,
        ),
    ):
        task = schedule_paper_pipeline("paper-1", pdf_path)
        await task
        await asyncio.sleep(0)

    mock_refine.assert_awaited_once_with("paper-1", pdf_path.resolve())
    assert isinstance(task, asyncio.Task)


@pytest.mark.asyncio
async def test_schedule_paper_pipeline_returns_asyncio_task(tmp_path: Path) -> None:
    pdf_path = tmp_path / "queued.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with patch(
        "backend.graph.workflow.run_paper_pipeline",
        new_callable=AsyncMock,
    ):
        task = schedule_paper_pipeline("paper-queued", pdf_path)

    assert isinstance(task, asyncio.Task)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
