"""Schedule single-paper LangGraph pipeline after HTTP upload (V1 in-process queue)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_head_refine_tasks: dict[str, asyncio.Task[None]] = {}


async def _run_pipeline_safe(paper_id: str, pdf_path: Path) -> None:
    from backend.graph.workflow import run_paper_pipeline

    try:
        await run_paper_pipeline(paper_id, pdf_path.resolve())
    except Exception:
        logger.exception("Paper pipeline failed for %s", paper_id)


async def _refine_head_safe(paper_id: str, pdf_path: Path) -> None:
    from backend.services.head_refine_service import refine_head_async

    try:
        await refine_head_async(paper_id, pdf_path.resolve())
    except Exception:
        logger.exception("Head refine failed for %s (pipeline continues)", paper_id)
    finally:
        _head_refine_tasks.pop(paper_id, None)


def ensure_head_refine_scheduled(paper_id: str, pdf_path: Path) -> None:
    """Start async head refine once per paper (parallel with LangGraph pipeline)."""
    existing = _head_refine_tasks.get(paper_id)
    if existing is not None and not existing.done():
        return
    resolved = pdf_path.resolve()
    _head_refine_tasks[paper_id] = asyncio.create_task(_refine_head_safe(paper_id, resolved))


def schedule_paper_pipeline(paper_id: str, pdf_path: Path) -> asyncio.Task[None]:
    """Enqueue LangGraph pipeline and async head refine (``asyncio.create_task``)."""
    resolved = pdf_path.resolve()
    ensure_head_refine_scheduled(paper_id, resolved)
    return asyncio.create_task(_run_pipeline_safe(paper_id, resolved))
