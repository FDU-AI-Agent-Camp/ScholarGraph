"""In-process asyncio Task registry for force abort (reextract / delete).

There is no Celery. Pipeline, head-refine, and full-extract tasks are tracked
so ``force=true`` can ``Task.cancel()`` before cascading cleanup.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_pipeline_tasks: dict[str, asyncio.Task[None]] = {}
_head_refine_tasks: dict[str, asyncio.Task[None]] = {}


def register_pipeline_task(paper_id: str, task: asyncio.Task[None]) -> None:
    """Replace any prior non-done pipeline task for *paper_id* and register *task*."""
    prior = _pipeline_tasks.get(paper_id)
    if prior is not None and prior is not task and not prior.done():
        prior.cancel()
    _pipeline_tasks[paper_id] = task


def unregister_pipeline_task(paper_id: str, task: asyncio.Task[None] | None = None) -> None:
    """Drop registry entry when the task finishes (ignore stale replacements)."""
    current = _pipeline_tasks.get(paper_id)
    if current is None:
        return
    if task is not None and current is not task:
        return
    _pipeline_tasks.pop(paper_id, None)


def get_pipeline_task(paper_id: str) -> asyncio.Task[None] | None:
    task = _pipeline_tasks.get(paper_id)
    if task is not None and not task.done():
        return task
    return None


def _task_is_live(task: asyncio.Task[None] | None) -> bool:
    """True when *task* is still executing (not done / not mid-cancel)."""
    if task is None or task.done():
        return False
    cancelling = getattr(task, "cancelling", None)
    if callable(cancelling):
        pending = cancelling()
        if isinstance(pending, int) and pending > 0:
            return False
    return True


def is_paper_work_alive(paper_id: str) -> bool:
    """Return whether in-process work for *paper_id* is still running.

    Used by the processing wall-clock watchdog dual-check: stale ``updated_at``
    alone must not tombstone a slow-but-alive LLM stage when the asyncio Task
    is still registered.
    """
    from backend.services.extract_worker import get_full_extraction_task

    return any(
        _task_is_live(task)
        for task in (
            get_pipeline_task(paper_id),
            get_head_refine_task(paper_id),
            get_full_extraction_task(paper_id),
        )
    )


def register_head_refine_task(paper_id: str, task: asyncio.Task[None]) -> None:
    prior = _head_refine_tasks.get(paper_id)
    if prior is not None and prior is not task and not prior.done():
        prior.cancel()
    _head_refine_tasks[paper_id] = task


def unregister_head_refine_task(paper_id: str, task: asyncio.Task[None] | None = None) -> None:
    current = _head_refine_tasks.get(paper_id)
    if current is None:
        return
    if task is not None and current is not task:
        return
    _head_refine_tasks.pop(paper_id, None)


def get_head_refine_task(paper_id: str) -> asyncio.Task[None] | None:
    task = _head_refine_tasks.get(paper_id)
    if task is not None and not task.done():
        return task
    return None


async def _cancel_task(task: asyncio.Task[None] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def cancel_paper_tasks(paper_id: str) -> None:
    """Cancel pipeline + head-refine + full-extract tasks for *paper_id* and await them."""
    from backend.services.extract_worker import cancel_full_extraction

    pipeline = get_pipeline_task(paper_id)
    head = get_head_refine_task(paper_id)
    await _cancel_task(pipeline)
    unregister_pipeline_task(paper_id, pipeline)
    await _cancel_task(head)
    unregister_head_refine_task(paper_id, head)
    await cancel_full_extraction(paper_id)
    logger.info("paper_tasks_cancelled", extra={"paper_id": paper_id})


def force_cancel_paper_work_sync(paper_id: str) -> None:
    """Cascading Kill Channel steps 1–2: inject CancelledError + evict concurrency claims.

    Cancels registered tasks **without** unregistering them so a subsequent
    ``abort_in_flight_pipeline`` / ``cancel_paper_tasks`` can still ``await``
    ``finally`` drain. Thread-safe enough for the dedicated watchdog OS thread.
    """
    from backend.rag.indexing_run_registry import get_indexing_run_registry
    from backend.services.extract_worker import get_full_extraction_task
    from backend.services.reextract_service import release_reextract_claim_for_abort

    pipeline = get_pipeline_task(paper_id)
    if pipeline is not None:
        pipeline.cancel()
    head = get_head_refine_task(paper_id)
    if head is not None:
        head.cancel()
    full = get_full_extraction_task(paper_id)
    if full is not None:
        full.cancel()
    get_indexing_run_registry().revoke(paper_id)
    release_reextract_claim_for_abort(paper_id)
    logger.info(
        "paper_work_force_cancelled_sync",
        extra={"paper_id": paper_id, "cascading_kill_channel": True},
    )


async def abort_in_flight_pipeline(paper_id: str) -> None:
    """Graceful termination: cancel tasks, await drain, evict indexing + reextract claims."""
    from backend.rag.indexing_run_registry import get_indexing_run_registry
    from backend.services.reextract_service import release_reextract_claim_for_abort

    await cancel_paper_tasks(paper_id)
    get_indexing_run_registry().revoke(paper_id)
    release_reextract_claim_for_abort(paper_id)


def reset_pipeline_task_registry() -> None:
    """Test helper: cancel and clear all registered pipeline/head tasks."""
    for task in list(_pipeline_tasks.values()):
        if not task.done():
            task.cancel()
    for task in list(_head_refine_tasks.values()):
        if not task.done():
            task.cancel()
    _pipeline_tasks.clear()
    _head_refine_tasks.clear()


# Typed alias for clarity in call sites that inject abort.
AbortFn = Callable[[str], Awaitable[None]]
