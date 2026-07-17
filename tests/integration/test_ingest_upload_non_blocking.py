# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Upload must return immediately; path-B head refine runs asynchronously."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.api.conftest import assert_success_envelope

VALID_PDF = b"%PDF-1.4\n% ScholarGraph upload non-blocking test"
UPLOAD_LATENCY_BUDGET_SECONDS = 2.0
HEAD_REFINE_BLOCK_SECONDS = 5.0


@pytest.mark.asyncio
async def test_http_upload_returns_before_slow_head_refine(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    refine_gate = asyncio.Event()

    async def slow_refine(paper_id: str, pdf_path: Path) -> None:
        await refine_gate.wait()

    with (
        patch(
            "backend.services.paper_pipeline_scheduler._refine_head_safe",
            side_effect=slow_refine,
        ),
        patch(
            "backend.graph.workflow.run_paper_pipeline",
            new_callable=AsyncMock,
        ),
    ):
        started = time.perf_counter()
        response = await api_client.post(
            "/api/v1/papers",
            files={"file": ("non-blocking.pdf", VALID_PDF, "application/pdf")},
        )
        elapsed = time.perf_counter() - started

    assert response.status_code == 201
    assert elapsed < UPLOAD_LATENCY_BUDGET_SECONDS
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["status"] == "pending"

    refine_gate.set()


@pytest.mark.asyncio
async def test_schedule_paper_pipeline_returns_without_awaiting_head_refine(
    tmp_path: Path,
) -> None:
    from backend.services.paper_pipeline_scheduler import schedule_paper_pipeline

    pdf_path = tmp_path / "queued.pdf"
    pdf_path.write_bytes(VALID_PDF)
    refine_started = asyncio.Event()

    async def slow_refine(paper_id: str, pdf_path_arg: Path) -> None:
        refine_started.set()
        await asyncio.sleep(HEAD_REFINE_BLOCK_SECONDS)

    with (
        patch(
            "backend.services.paper_pipeline_scheduler._refine_head_safe",
            side_effect=slow_refine,
        ),
        patch(
            "backend.graph.workflow.run_paper_pipeline",
            new_callable=AsyncMock,
        ),
    ):
        started = time.perf_counter()
        task = schedule_paper_pipeline("paper-fast", pdf_path)
        elapsed = time.perf_counter() - started

    assert isinstance(task, asyncio.Task)
    assert elapsed < 0.5
    await asyncio.wait_for(refine_started.wait(), timeout=1.0)
    await task
