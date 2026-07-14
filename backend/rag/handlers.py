"""Official RAG event handlers and indexing entry points (P10)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from backend.events.bus import get_event_bus
from backend.events.pipeline_finalized_contract import (
    PipelineFinalizedContractError,
    pipeline_finalized_correlation_id,
    validate_pipeline_finalized_payload,
)
from backend.events.types import EventType, PipelineFinalized, RagIndexed
from backend.rag.chunking import chunk_text
from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service

logger = logging.getLogger(__name__)

RAG_INDEX_WARNING_CODE = "rag_index_failed"
RAG_PIPELINE_HANDLER_NAME = "on_pipeline_finalized_for_rag"

_OFFICIAL_HANDLER_REGISTERED = False
_INDEX_LOCKS: dict[str, asyncio.Lock] = {}
_INDEX_LOCKS_GUARD = asyncio.Lock()


async def _lock_for_paper(paper_id: str) -> asyncio.Lock:
    async with _INDEX_LOCKS_GUARD:
        lock = _INDEX_LOCKS.get(paper_id)
        if lock is None:
            lock = asyncio.Lock()
            _INDEX_LOCKS[paper_id] = lock
        return lock


async def index_paper_for_rag(
    paper_id: str,
    *,
    full_text: str,
    graph: UnifiedPaperGraph,
    vector_store: VectorStore | None = None,
    suppress_errors: bool = True,
    page_break_offsets: list[int] | None = None,
) -> bool:
    """Build or replace the RAG vector index for one finalized paper (idempotent upsert)."""

    if not isinstance(paper_id, str) or not paper_id.strip():
        raise ValueError("paper_id must be a non-empty string")
    if graph.paper_id != paper_id:
        raise ValueError(f"graph.paper_id ({graph.paper_id!r}) does not match paper_id ({paper_id!r})")

    from backend.config import get_settings

    lock = await _lock_for_paper(paper_id)
    async with lock:
        store = vector_store or VectorStore(paper_service=get_paper_service())
        try:
            settings = get_settings()
            chunks = chunk_text(
                paper_id,
                full_text,
                chunk_size_chars=settings.rag_chunk_size_chars,
                chunk_overlap_ratio=settings.rag_chunk_overlap_ratio,
                min_chunk_chars=settings.rag_chunk_min_chunk_chars,
                min_soft_boundary_window_chars=settings.rag_chunk_min_soft_boundary_window_chars,
                include_references=settings.rag_chunk_include_references,
                page_break_offsets=page_break_offsets,
            )
            entities = graph_to_entities(paper_id, graph)
            relations = graph_to_relations(paper_id, graph)
            # replace_paper_index is upsert-style (new run_id then cutover).
            await store.replace_paper_index(
                paper_id,
                chunks=chunks,
                entities=entities,
                relations=relations,
            )
        except Exception as exc:
            exc_type_name = type(exc).__name__
            exc_msg = str(exc)

            logger.exception(
                RAG_INDEX_WARNING_CODE,
                extra={
                    "paper_id": paper_id,
                    "exc_type": exc_type_name,
                    "exc_msg": exc_msg,
                },
            )
            _record_index_warning(paper_id, exc_type_name, exc_msg)

            if not suppress_errors:
                raise
            return False
        return True


def _record_index_warning(paper_id: str, exc_type_name: str, exc_msg: str) -> None:
    """Persist a machine-readable RAG index warning on the paper status snapshot."""

    try:
        get_paper_service().record_extract_warnings(paper_id, [RAG_INDEX_WARNING_CODE])
    except Exception:
        logger.exception("failed_to_record_rag_index_warning", extra={"paper_id": paper_id})


async def _promote_terminal_status(event: PipelineFinalized, *, success: bool) -> None:
    """Promote paper status via async repo I/O (safe inside the EventBus worker)."""
    from datetime import UTC, datetime

    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PaperStatusData, PipelineStage
    from backend.services.paper_service import get_paper_service
    from backend.services.pipeline_status_service import (
        DEFAULT_STAGE_MESSAGES,
        validate_failed_error_fields,
        validate_status_contract,
    )

    paper_service = get_paper_service()
    terminal = event.terminal_status
    if terminal not in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS}:
        terminal = PaperStatus.READY

    append_warnings = [RAG_INDEX_WARNING_CODE] if not success else None
    if not success:
        status = PaperStatus.READY_WITH_WARNINGS
        message = "建图完成，但向量索引构建失败"
    elif terminal == PaperStatus.READY_WITH_WARNINGS:
        status = PaperStatus.READY_WITH_WARNINGS
        message = event.warning_message or "建图完成，但图谱置信度未达门控，请复核"
    else:
        status = PaperStatus.READY
        message = DEFAULT_STAGE_MESSAGES[PipelineStage.READY]

    stage = PipelineStage.READY
    percent = STAGE_PERCENT[PipelineStage.READY]
    validate_status_contract(status=status, stage=stage, percent=percent)
    validate_failed_error_fields(status=status, error_code=None, failed_during=None)

    now = datetime.now(UTC)
    existing = await paper_service._pipeline_repo.get_latest(event.paper_id)
    if existing is None:
        msg = f"pipeline run missing for paper {event.paper_id}"
        raise RuntimeError(msg)
    merged_extract_warnings = list(existing.extract_warnings)
    if append_warnings:
        merged_extract_warnings = list(dict.fromkeys([*merged_extract_warnings, *append_warnings]))
    snapshot = PaperStatusData(
        paper_id=event.paper_id,
        status=status,
        percent=percent,
        stage=stage,
        message=message,
        updated_at=now,
        preview_available=bool(existing.preview_available),
        error_code=None,
        failed_during=None,
        head_refine_warnings=list(existing.head_refine_warnings),
        classify_warnings=list(existing.classify_warnings),
        extract_warnings=merged_extract_warnings,
    )
    await paper_service._pipeline_repo.save_status(event.paper_id, snapshot)


async def on_pipeline_finalized_for_rag(event: PipelineFinalized) -> None:
    """Official exclusive subscriber: contract audit → index → promote READY → RagIndexed."""
    correlation_id = pipeline_finalized_correlation_id(event.paper_id)
    logger.info(
        "pipeline_finalized_consumed",
        extra={
            "correlation_id": correlation_id,
            "paper_id": event.paper_id,
            "event_type": EventType.PIPELINE_FINALIZED.value,
            "channel": "event_bus_subscriber",
            "handler": RAG_PIPELINE_HANDLER_NAME,
        },
    )

    try:
        graph = await validate_pipeline_finalized_payload(event)
    except PipelineFinalizedContractError:
        logger.exception(
            "pipeline_finalized_contract_rejected",
            extra={
                "correlation_id": correlation_id,
                "paper_id": event.paper_id,
                "event_type": EventType.PIPELINE_FINALIZED.value,
            },
        )
        # Avoid leaving papers stuck in ``indexing``; do not re-raise (would double-write via
        # EventBus error hook and contend on SQLite).
        await _promote_terminal_status(event, success=False)
        get_event_bus().publish_sync(
            RagIndexed(
                paper_id=event.paper_id,
                success=False,
                terminal_status=PaperStatus.READY_WITH_WARNINGS,
            ),
        )
        return

    logger.info(
        "pipeline_finalized_contract_ok",
        extra={
            "correlation_id": correlation_id,
            "paper_id": event.paper_id,
            "full_text_chars": len(event.full_text),
            "graph_node_count": len(graph.nodes),
            "graph_edge_count": len(graph.edges),
        },
    )

    from backend.services.rag_index_service import get_rag_index_service

    try:
        indexed = await get_rag_index_service().index_paper_for_rag_async(
            event.paper_id,
            full_text=event.full_text,
            graph=graph,
            page_break_offsets=event.page_break_offsets,
        )
        success = True if indexed is None else bool(indexed)
    except Exception:
        logger.exception(
            "pipeline_finalized_rag_index_failed",
            extra={
                "correlation_id": correlation_id,
                "paper_id": event.paper_id,
                "event_type": EventType.PIPELINE_FINALIZED.value,
            },
        )
        success = False

    await _promote_terminal_status(event, success=success)
    get_event_bus().publish_sync(
        RagIndexed(
            paper_id=event.paper_id,
            success=success,
            terminal_status=event.terminal_status if success else PaperStatus.READY_WITH_WARNINGS,
        ),
    )


def _is_rag_indexing_handler(handler: Callable[..., Awaitable[None] | None]) -> bool:
    name = getattr(handler, "__name__", "")
    qual = getattr(handler, "__qualname__", "")
    module = getattr(handler, "__module__", "")
    blob = f"{module}:{qual}:{name}".lower()
    return "rag" in blob and (
        "index" in blob or "pipeline_finalized" in blob or "on_pipeline_finalized" in blob
    )


def assert_exclusive_rag_pipeline_subscriber() -> None:
    """Startup/runtime guard: at most one RAG indexing subscriber on PIPELINE_FINALIZED."""
    bus = get_event_bus()
    handlers = list(bus._handlers.get(EventType.PIPELINE_FINALIZED, []))
    rag_handlers = [handler for handler in handlers if _is_rag_indexing_handler(handler)]
    if len(rag_handlers) > 1:
        names = [getattr(handler, "__qualname__", repr(handler)) for handler in rag_handlers]
        msg = (
            "Exclusive RAG subscription violated for PIPELINE_FINALIZED: "
            f"found {len(rag_handlers)} handlers {names}. "
            "Keep only backend.rag.handlers.on_pipeline_finalized_for_rag."
        )
        raise RuntimeError(msg)
    if rag_handlers and getattr(rag_handlers[0], "__name__", "") != RAG_PIPELINE_HANDLER_NAME:
        name = getattr(rag_handlers[0], "__name__", "?")
        msg = (
            f"PIPELINE_FINALIZED RAG handler must be {RAG_PIPELINE_HANDLER_NAME!r}, "
            f"got {name!r}"
        )
        raise RuntimeError(msg)


def register_rag_pipeline_finalized_handler(*, force: bool = False) -> None:
    """Bind the official exclusive RAG subscriber (idempotent)."""
    global _OFFICIAL_HANDLER_REGISTERED

    bus = get_event_bus()
    handlers = bus._handlers[EventType.PIPELINE_FINALIZED]
    if on_pipeline_finalized_for_rag in handlers:
        if not force:
            assert_exclusive_rag_pipeline_subscriber()
            return
        handlers.remove(on_pipeline_finalized_for_rag)

    # Strip any legacy temporary_* subscribers if present during transition windows.
    stale = [
        handler
        for handler in list(handlers)
        if "temporary" in getattr(handler, "__name__", "").lower()
        or "temporary" in getattr(handler, "__qualname__", "").lower()
    ]
    for handler in stale:
        handlers.remove(handler)

    bus.subscribe(EventType.PIPELINE_FINALIZED, on_pipeline_finalized_for_rag)
    _OFFICIAL_HANDLER_REGISTERED = True
    assert_exclusive_rag_pipeline_subscriber()


def unregister_rag_pipeline_finalized_handler() -> None:
    """Remove the official handler (tests that install custom subscribers only)."""
    global _OFFICIAL_HANDLER_REGISTERED

    bus = get_event_bus()
    handlers = bus._handlers[EventType.PIPELINE_FINALIZED]
    if on_pipeline_finalized_for_rag in handlers:
        handlers.remove(on_pipeline_finalized_for_rag)
    _OFFICIAL_HANDLER_REGISTERED = False
