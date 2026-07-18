# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Official RAG event handlers and indexing entry points (P10 + P13).

P10: ``PipelineFinalized`` → index → promote terminal status + ``RagIndexed``.
P13: ``wait_for`` + heartbeat; on timeout revoke via ``IndexingRunRegistry`` and
schedule compensating ``delete_run`` (sticky revoke so cancel-then-timeout still
yields a run_id). Macro stuck-INDEXING heal lives in ``indexing_watchdog``.
"""

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
from backend.events.types import EventType, PipelineFinalized
from backend.rag.chunking import chunk_text
from backend.rag.indexing import graph_to_entities, graph_to_relations
from backend.rag.vector_store import VectorStore
from backend.schemas.graph import UnifiedPaperGraph
from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
from backend.services.paper_service import get_paper_service

logger = logging.getLogger(__name__)

RAG_INDEX_WARNING_CODE = "rag_index_failed"
RAG_INDEX_TIMEOUT_WARNING = "rag_index_timeout"
RAG_PIPELINE_HANDLER_NAME = "on_pipeline_finalized_for_rag"
# Delayed retries so late to_thread upserts after wait_for cancel are still erased.
ORPHAN_RUN_CLEANUP_DELAYS_SECONDS: tuple[float, ...] = (0.0, 5.0, 10.0)

_OFFICIAL_HANDLER_REGISTERED = False
_INDEX_LOCKS: dict[str, asyncio.Lock] = {}
_INDEX_LOCKS_GUARD = asyncio.Lock()
_ORPHAN_CLEANUP_TASKS: set[asyncio.Task[None]] = set()


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
            await _record_index_warning(paper_id, exc_type_name, exc_msg)

            if not suppress_errors:
                raise
            return False
        return True


async def _record_index_warning(paper_id: str, exc_type_name: str, exc_msg: str) -> None:
    """Persist a machine-readable RAG index warning on the paper status snapshot."""
    from backend.services.paper_warning_service import WarningType, get_paper_warning_service

    _ = exc_type_name, exc_msg
    try:
        await get_paper_warning_service().record(paper_id, WarningType.EXTRACT, [RAG_INDEX_WARNING_CODE])
    except Exception:
        logger.exception("failed_to_record_rag_index_warning", extra={"paper_id": paper_id})


async def _heartbeat_loop(paper_id: str, stop_event: asyncio.Event, *, interval_seconds: float) -> None:
    """Keep indexing_heartbeat fresh while a long index build is still running."""

    pipeline_ops = get_paper_pipeline_ops_service()
    while not stop_event.is_set():
        try:
            await pipeline_ops.touch_indexing_heartbeat(paper_id)
        except Exception:
            logger.exception("indexing_heartbeat_touch_failed", extra={"paper_id": paper_id})
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


async def _compensate_revoked_index_run(
    paper_id: str,
    run_id: str,
    *,
    delays_seconds: tuple[float, ...] = ORPHAN_RUN_CLEANUP_DELAYS_SECONDS,
) -> None:
    """Delete a revoked run_id with delayed retries (compensating transaction).

    Does not delete a different active run left by a later successful re-index.
    If the revoked run somehow became active, clear the active pointer first.
    """
    from backend.rag.indexing_run_registry import get_indexing_run_registry

    registry = get_indexing_run_registry()
    store = VectorStore(paper_service=get_paper_service())
    for delay in delays_seconds:
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            active = get_paper_service().get_active_run_id(paper_id)
            if active == run_id:
                # Late activate won the race — clear pointer to SQL NULL, keep graph READY.
                get_paper_service().set_active_run_id(paper_id, None)
            await store.delete_run(paper_id, run_id)
            logger.info(
                "orphan_index_run_cleanup",
                extra={"paper_id": paper_id, "run_id": run_id, "delay_seconds": delay},
            )
        except Exception:
            logger.exception(
                "orphan_index_run_cleanup_failed",
                extra={"paper_id": paper_id, "run_id": run_id, "delay_seconds": delay},
            )
    registry.clear(paper_id, run_id)


def _schedule_orphan_run_cleanup(paper_id: str, run_id: str) -> None:
    """Fire-and-forget compensating cleanup after wait_for timeout."""
    task = asyncio.create_task(
        _compensate_revoked_index_run(paper_id, run_id),
        name=f"rag-orphan-cleanup:{paper_id}:{run_id}",
    )
    _ORPHAN_CLEANUP_TASKS.add(task)
    task.add_done_callback(_ORPHAN_CLEANUP_TASKS.discard)


def _revoke_and_schedule_orphan_cleanup(paper_id: str) -> str | None:
    """Revoke the in-flight (or already sticky-revoked) run and schedule cleanup.

    ``IndexingRunRegistry.revoke(paper_id)`` still returns the id when cancel /
    refuse already moved it into the revoke set, so delayed compensate can run.
    """
    from backend.rag.indexing_run_registry import get_indexing_run_registry

    revoked_run_id = get_indexing_run_registry().revoke(paper_id)
    if revoked_run_id is not None:
        _schedule_orphan_run_cleanup(paper_id, revoked_run_id)
    return revoked_run_id


async def _index_with_heartbeat_and_timeout(
    paper_id: str,
    *,
    full_text: str,
    graph: UnifiedPaperGraph,
    page_break_offsets: list[int] | None,
    timeout_seconds: float,
    heartbeat_interval_seconds: float,
    index_fn: Callable[..., Awaitable[bool | None]],
) -> bool | None:
    """Run index build under wait_for while pulsing indexing_heartbeat."""
    stop_event = asyncio.Event()
    # Initial pulse so watchdog sees an alive task immediately.
    try:
        await get_paper_pipeline_ops_service().touch_indexing_heartbeat(paper_id)
    except Exception:
        logger.exception("indexing_heartbeat_initial_touch_failed", extra={"paper_id": paper_id})

    hb_task = asyncio.create_task(
        _heartbeat_loop(paper_id, stop_event, interval_seconds=heartbeat_interval_seconds),
        name=f"rag-index-heartbeat:{paper_id}",
    )
    try:
        return await asyncio.wait_for(
            index_fn(
                paper_id,
                full_text=full_text,
                graph=graph,
                page_break_offsets=page_break_offsets,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        # Revoke before / as cancel unwinds so late set_active_run_id is gated.
        _revoke_and_schedule_orphan_cleanup(paper_id)
        raise
    finally:
        stop_event.set()
        hb_task.cancel()
        try:
            await hb_task
        except asyncio.CancelledError:
            pass


async def _promote_terminal_status(
    event: PipelineFinalized,
    *,
    success: bool,
    warning_codes: list[str] | None = None,
    message_override: str | None = None,
) -> None:
    """Promote via PaperService facade (includes RagIndexed publish).

    Idempotent when macro watchdog (or a prior attempt) already moved the paper to
    ``ready`` / ``ready_with_warnings``: swallow ``InvalidStateTransitionError`` so
    EventBus does not persist a fake ``event_handler_failed`` warning.
    """
    from backend.schemas.paper import PaperStatus
    from backend.services.errors import InvalidStateTransitionError

    pipeline_ops = get_paper_pipeline_ops_service()
    try:
        await pipeline_ops.promote_paper_to_terminal_status(
            event.paper_id,
            success=success,
            preferred_terminal=event.terminal_status,
            warning_message=event.warning_message,
            warning_codes=warning_codes,
            message_override=message_override,
            publish_rag_indexed=True,
        )
    except InvalidStateTransitionError as exc:
        snapshot = await pipeline_ops.get_pipeline_snapshot(event.paper_id)
        if snapshot is not None and snapshot.status in {
            PaperStatus.READY,
            PaperStatus.READY_WITH_WARNINGS,
        }:
            logger.info(
                "pipeline_finalized_promote_idempotent_skip",
                extra={
                    "paper_id": event.paper_id,
                    "current_status": snapshot.status.value,
                    "from_status": exc.from_status,
                    "to_status": exc.to_status,
                    "reason": "already_terminal",
                },
            )
            return
        raise


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
        # EventBus error hook and contend on SQLite). Facades publish RagIndexed.
        await _promote_terminal_status(event, success=False)
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

    from backend.config import get_settings
    from backend.services.rag_index_service import get_rag_index_service

    settings = get_settings()
    timeout_seconds = settings.rag_single_index_timeout_seconds
    success = False
    failure_warnings: list[str] | None = None
    failure_message: str | None = None

    try:
        indexed = await _index_with_heartbeat_and_timeout(
            event.paper_id,
            full_text=event.full_text,
            graph=graph,
            page_break_offsets=event.page_break_offsets,
            timeout_seconds=timeout_seconds,
            heartbeat_interval_seconds=settings.rag_indexing_heartbeat_interval_seconds,
            index_fn=get_rag_index_service().index_paper_for_rag_async,
        )
        success = True if indexed is None else bool(indexed)
        if not success:
            failure_warnings = [RAG_INDEX_WARNING_CODE]
    except TimeoutError:
        # Defensive second revoke: wait_for path already revoked; keeps cleanup if
        # index_fn raised TimeoutError without going through that helper.
        _revoke_and_schedule_orphan_cleanup(event.paper_id)
        logger.error(
            "pipeline_finalized_rag_index_timeout",
            extra={
                "correlation_id": correlation_id,
                "paper_id": event.paper_id,
                "timeout_seconds": timeout_seconds,
                "event_type": EventType.PIPELINE_FINALIZED.value,
            },
        )
        success = False
        failure_warnings = [RAG_INDEX_TIMEOUT_WARNING]
        failure_message = f"建图完成，但向量索引超时（>{timeout_seconds:.0f}s）"
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
        failure_warnings = [RAG_INDEX_WARNING_CODE]

    await _promote_terminal_status(
        event,
        success=success,
        warning_codes=failure_warnings,
        message_override=failure_message,
    )


def _is_rag_indexing_handler(handler: Callable[..., Awaitable[None] | None]) -> bool:
    name = getattr(handler, "__name__", "")
    qual = getattr(handler, "__qualname__", "")
    module = getattr(handler, "__module__", "")
    blob = f"{module}:{qual}:{name}".lower()
    return "rag" in blob and ("index" in blob or "pipeline_finalized" in blob or "on_pipeline_finalized" in blob)


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
        msg = f"PIPELINE_FINALIZED RAG handler must be {RAG_PIPELINE_HANDLER_NAME!r}, got {name!r}"
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
