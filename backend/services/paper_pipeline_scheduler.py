"""Schedule single-paper LangGraph pipeline after HTTP upload (V1 in-process queue)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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


def schedule_paper_pipeline(paper_id: str, pdf_path: Path) -> asyncio.Task[None]:
    """Enqueue LangGraph pipeline and async head refine (``asyncio.create_task``)."""
    resolved = pdf_path.resolve()
    asyncio.create_task(_refine_head_safe(paper_id, resolved))
    return asyncio.create_task(_run_pipeline_safe(paper_id, resolved))
