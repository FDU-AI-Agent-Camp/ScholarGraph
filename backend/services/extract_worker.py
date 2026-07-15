"""Background full-graph extraction worker (Slice 2).

After the LangGraph pipeline reaches the extract stage, long papers are handed
off to a background ``asyncio.Task``.  The task runs the full chunked
extraction with RPM/TPM rate limiting and finalizes the pipeline when done.
The frontend continues to poll ``GET /papers/{id}/status``; the status stays
``processing`` at ``extracting`` stage until the background task marks it ready
or failed.
"""

from __future__ import annotations

import asyncio
import logging

from backend.agents.extract_heuristic import extract_title
from backend.agents.extractor import _extract_chunked_two_phase
from backend.config import Settings, get_settings
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import get_pipeline_completion_service
from backend.services.pipeline_status_service import get_pipeline_status_service

logger = logging.getLogger(__name__)

_full_extract_tasks: dict[str, asyncio.Task[None]] = {}


async def _run_full_extraction(
    paper_id: str,
    full_text: str,
    paradigm: Paradigm,
    classification: ParadigmClassification,
    *,
    head_context: str | None,
    settings: Settings,
) -> None:
    """Run full extraction and finalize the pipeline."""
    status_service = get_pipeline_status_service()
    completion_service = get_pipeline_completion_service()
    paper_service = get_paper_service()

    try:
        current = await paper_service.get_status(paper_id)
        if current.status in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS, PaperStatus.FAILED}:
            return
        if not (current.status == PaperStatus.PROCESSING and current.stage == PipelineStage.EXTRACTING):
            status_service.advance_stage(
                paper_id,
                stage=PipelineStage.EXTRACTING,
                message="后台全量抽取进行中",
            )

        result = await _extract_chunked_two_phase(
            full_text,
            paradigm,
            paper_id=paper_id,
            title=extract_title(full_text),
            head_context=head_context,
            settings=settings,
        )

        graph = result.graph
        completion_service.finalize(
            paper_id,
            graph_data=graph.model_dump(mode="json"),
            classification_data=classification.model_dump(mode="json"),
            full_text=full_text,
        )
        logger.info(
            "background_full_extraction_complete",
            extra={"paper_id": paper_id, "nodes": len(graph.nodes), "edges": len(graph.edges)},
        )
    except ServiceError as exc:
        logger.exception("background_full_extraction_failed", extra={"paper_id": paper_id})
        paper_service.fail_pipeline(
            paper_id,
            message=exc.message,
            error_code=exc.code,
            failed_during=PipelineStage.EXTRACTING,
        )
    except Exception as exc:
        logger.exception("background_full_extraction_failed", extra={"paper_id": paper_id})
        paper_service.fail_pipeline(
            paper_id,
            message=f"后台全量抽取失败: {exc}",
            error_code=PIPELINE_FAILED_CODE,
            failed_during=PipelineStage.EXTRACTING,
        )
    finally:
        _full_extract_tasks.pop(paper_id, None)


def schedule_full_extraction(
    paper_id: str,
    full_text: str,
    paradigm: Paradigm,
    classification: ParadigmClassification,
    *,
    head_context: str | None = None,
    settings: Settings | None = None,
) -> asyncio.Task[None]:
    """Start (or return) the background full-extraction task for *paper_id*.

        The task is idempotent: only one background extraction runs per paper at a
    time.
    """
    existing = _full_extract_tasks.get(paper_id)
    if existing is not None and not existing.done():
        logger.debug("full_extraction_already_scheduled", extra={"paper_id": paper_id})
        return existing

    cfg = settings or get_settings()
    task = asyncio.create_task(
        _run_full_extraction(
            paper_id,
            full_text,
            paradigm,
            classification,
            head_context=head_context,
            settings=cfg,
        ),
        name=f"full-extract-{paper_id}",
    )
    _full_extract_tasks[paper_id] = task
    logger.info("background_full_extraction_scheduled", extra={"paper_id": paper_id})
    return task


def get_full_extraction_task(paper_id: str) -> asyncio.Task[None] | None:
    """Return the active background extraction task for *paper_id*, if any."""
    task = _full_extract_tasks.get(paper_id)
    if task is not None and not task.done():
        return task
    return None


async def cancel_full_extraction(paper_id: str) -> None:
    """Cancel and await the background full-extraction task for *paper_id*, if any."""
    task = _full_extract_tasks.pop(paper_id, None)
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def reset_extract_worker() -> None:
    """Cancel in-flight work and drop registry entries (sync; does not await CancelledError)."""
    for task in list(_full_extract_tasks.values()):
        if not task.done():
            task.cancel()
    _full_extract_tasks.clear()


async def areset_extract_worker() -> None:
    """Cancel and await background extraction tasks (preferred in async test fixtures)."""
    tasks = list(_full_extract_tasks.values())
    _full_extract_tasks.clear()
    for task in tasks:
        if not task.done():
            task.cancel()
    if not tasks:
        return
    await asyncio.gather(*tasks, return_exceptions=True)
