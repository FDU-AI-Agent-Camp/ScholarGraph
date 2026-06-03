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


def schedule_paper_pipeline(paper_id: str, pdf_path: Path) -> asyncio.Task[None]:
    """Enqueue pipeline on the current event loop (``asyncio.create_task``)."""
    return asyncio.create_task(_run_pipeline_safe(paper_id, pdf_path))
