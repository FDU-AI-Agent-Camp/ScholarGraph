# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Boundary logging observability for Wave-2 vector cleanup sweep."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.rag.wipe_vector_sweep import _execute_wave2_job, reset_wipe_sweep_tasks_for_tests

_LOGGER = "backend.rag.wipe_vector_sweep"


@pytest.fixture(autouse=True)
def _reset_sweep_tasks() -> None:
    reset_wipe_sweep_tasks_for_tests()
    yield
    reset_wipe_sweep_tasks_for_tests()


@pytest.mark.asyncio
async def test_wipe_vector_run_failure_logs_structured_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    paper_id = "paper-wipe-001"
    run_id = "run_orphan_001"
    delays = (0.0, 5.0, 10.0)

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER),
        patch(
            "backend.rag.handlers._compensate_revoked_index_run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("chroma delete_run failed"),
        ),
        patch(
            "backend.rag.wipe_vector_sweep.get_vector_cleanup_queue_repository",
        ) as repo_factory,
    ):
        repo_factory.return_value.delete_by_paper_run_sync = MagicMock()
        await _execute_wave2_job(paper_id, run_id, delays_seconds=delays)

    records = [record for record in caplog.records if record.getMessage() == "wipe_vector_run_failed"]
    assert len(records) == 1
    log_record = records[0]
    assert log_record.paper_id == paper_id
    assert log_record.run_id == run_id
    assert log_record.attempt == len(delays)
    assert log_record.error == "chroma delete_run failed"
    assert log_record.error_type == "RuntimeError"
