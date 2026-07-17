# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Schedule single-paper LangGraph pipeline after HTTP upload (V1 in-process queue)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.services.pipeline_task_registry import (
    register_head_refine_task,
    register_pipeline_task,
    unregister_head_refine_task,
    unregister_pipeline_task,
)

logger = logging.getLogger(__name__)


async def _run_pipeline_safe(paper_id: str, pdf_path: Path) -> None:
    from backend.graph.workflow import run_paper_pipeline

    task = asyncio.current_task()
    try:
        await run_paper_pipeline(paper_id, pdf_path.resolve())
    except asyncio.CancelledError:
        logger.info("Paper pipeline cancelled for %s", paper_id)
        raise
    except Exception:
        logger.exception("Paper pipeline failed for %s", paper_id)
    finally:
        unregister_pipeline_task(paper_id, task if isinstance(task, asyncio.Task) else None)


async def _refine_head_safe(paper_id: str, pdf_path: Path) -> None:
    from backend.services.head_refine_service import refine_head_async

    task = asyncio.current_task()
    try:
        await refine_head_async(paper_id, pdf_path.resolve())
    except asyncio.CancelledError:
        logger.info("Head refine cancelled for %s", paper_id)
        raise
    except Exception:
        logger.exception("Head refine failed for %s (pipeline continues)", paper_id)
    finally:
        unregister_head_refine_task(paper_id, task if isinstance(task, asyncio.Task) else None)


def ensure_head_refine_scheduled(paper_id: str, pdf_path: Path) -> None:
    """Start async head refine once per paper (parallel with LangGraph pipeline)."""
    from backend.services.pipeline_task_registry import get_head_refine_task

    existing = get_head_refine_task(paper_id)
    if existing is not None:
        return
    resolved = pdf_path.resolve()
    task = asyncio.create_task(_refine_head_safe(paper_id, resolved))
    register_head_refine_task(paper_id, task)


def schedule_paper_pipeline(paper_id: str, pdf_path: Path) -> asyncio.Task[None]:
    """Enqueue LangGraph pipeline and async head refine (``asyncio.create_task``)."""
    resolved = pdf_path.resolve()
    ensure_head_refine_scheduled(paper_id, resolved)
    task = asyncio.create_task(_run_pipeline_safe(paper_id, resolved))
    register_pipeline_task(paper_id, task)
    return task
