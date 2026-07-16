"""In-process active task registry for force abort."""

from __future__ import annotations

import asyncio

import pytest
from backend.services.pipeline_task_registry import (
    abort_in_flight_pipeline,
    cancel_paper_tasks,
    get_pipeline_task,
    register_pipeline_task,
    reset_pipeline_task_registry,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_pipeline_task_registry()
    yield
    reset_pipeline_task_registry()


@pytest.mark.asyncio
async def test_cancel_paper_tasks_cancels_registered_pipeline_task() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _hang() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(_hang())
    register_pipeline_task("paper-reg-1", task)
    assert get_pipeline_task("paper-reg-1") is task
    await started.wait()

    await cancel_paper_tasks("paper-reg-1")
    assert cancelled.is_set()
    assert get_pipeline_task("paper-reg-1") is None


@pytest.mark.asyncio
async def test_abort_in_flight_revokes_indexing_registry() -> None:
    from backend.rag.indexing_run_registry import get_indexing_run_registry

    registry = get_indexing_run_registry()
    registry.begin("paper-revoke-1", "run-abc")
    assert registry.may_activate("paper-revoke-1", "run-abc") is True
    await abort_in_flight_pipeline("paper-revoke-1")
    assert registry.may_activate("paper-revoke-1", "run-abc") is False
