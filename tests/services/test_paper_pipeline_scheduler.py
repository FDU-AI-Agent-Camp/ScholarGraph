"""Upload pipeline scheduling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline


@pytest.mark.asyncio
async def test_schedule_paper_pipeline_invokes_run_paper_pipeline(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    with patch(
        "backend.graph.workflow.run_paper_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        task = schedule_paper_pipeline("paper-1", pdf_path)
        await task

    mock_run.assert_awaited_once_with("paper-1", pdf_path.resolve())


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
