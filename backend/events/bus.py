"""Lightweight in-process event bus for cross-module decoupling."""

from __future__ import annotations

import asyncio
import logging
import threading
import weakref
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from backend.events.types import EventType
from backend.repositories.async_bridge import (
    get_registered_main_event_loop,
    get_registered_main_loop_thread_id,
    run_async,
)

logger = logging.getLogger(__name__)

WORKER_CANCEL_TIMEOUT_SECONDS = 5.0

EventHandler = Callable[[Any], Awaitable[None] | None]
HandlerErrorCallback = Callable[[EventType, Exception, Any], Awaitable[None] | None]

_ALL_BUSES: weakref.WeakSet[EventBus] = weakref.WeakSet()


class EventBus:
    """Minimal pub/sub bus backed by an asyncio queue."""

    def __init__(self, *, on_handler_error: HandlerErrorCallback | None = None) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[Any] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._on_handler_error = on_handler_error
        _ALL_BUSES.add(self)

    def set_handler_error_callback(self, callback: HandlerErrorCallback | None) -> None:
        """Install optional hook invoked when a subscriber raises (D12 observability)."""
        self._on_handler_error = callback

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        await self._ensure_queue()
        assert self._queue is not None
        await self._queue.put(event)

    def publish_sync(self, event: Any) -> None:
        """Enqueue from synchronous callers; handlers run asynchronously (fire-and-forget)."""

        async def _publish() -> None:
            await self.publish(event)

        main_loop = get_registered_main_event_loop()
        main_loop_thread_id = get_registered_main_loop_thread_id()
        if (
            main_loop is not None
            and main_loop.is_running()
            and main_loop_thread_id is not None
            and threading.get_ident() != main_loop_thread_id
        ):
            asyncio.run_coroutine_threadsafe(_publish(), main_loop)
            return

        run_async(_publish())

    def drain_sync(self) -> None:
        """Block until queued events are processed (tests / scripts)."""
        run_async(self.drain())

    async def astop_worker(self) -> None:
        """Cancel the worker and await completion across loop ownership (D17)."""
        worker_task = self._worker_task
        self._worker_task = None
        self._queue = None
        if worker_task is None or worker_task.done():
            return
        worker_task.cancel()
        worker_loop = worker_task.get_loop()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if worker_loop.is_closed():
            worker_task._log_destroy_pending = False  # type: ignore[attr-defined]
            return
        if running_loop is worker_loop:
            await _await_cancelled_task(worker_task)
            return
        if worker_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_await_cancelled_task(worker_task), worker_loop)
            try:
                await asyncio.to_thread(future.result, WORKER_CANCEL_TIMEOUT_SECONDS)
            except Exception:
                worker_task._log_destroy_pending = False  # type: ignore[attr-defined]
                logger.debug("event_bus_worker_astop_failed", exc_info=True)
            return
        try:
            await asyncio.to_thread(worker_loop.run_until_complete, _await_cancelled_task(worker_task))
        except Exception:
            worker_task._log_destroy_pending = False  # type: ignore[attr-defined]
            logger.debug("event_bus_worker_astop_failed", exc_info=True)

    def _stop_worker(self) -> None:
        """Tear down the background worker (tests / application shutdown).

        Prefer ``await astop_worker()`` when called from the worker's running loop.
        Same-loop sync stop only schedules cancel collection to avoid
        ``run_coroutine_threadsafe`` deadlocks (D17).
        """
        worker_task = self._worker_task
        self._worker_task = None
        self._queue = None
        if worker_task is None or worker_task.done():
            return
        worker_task.cancel()
        try:
            loop = worker_task.get_loop()
            if loop.is_closed():
                # Worker can never finish cleaning CancelledError — silence GC warn (D17).
                worker_task._log_destroy_pending = False  # type: ignore[attr-defined]
                return
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop is loop:
                # Cannot block-wait on the same loop; schedule await so CancelledError
                # is collected on the next tick (async fixtures should prefer astop_worker).
                loop.create_task(
                    _await_cancelled_task(worker_task),
                    name="event_bus_worker_cancel",
                )
                return
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_await_cancelled_task(worker_task), loop)
                future.result(timeout=WORKER_CANCEL_TIMEOUT_SECONDS)
            else:
                loop.run_until_complete(_await_cancelled_task(worker_task))
        except Exception:
            worker_task._log_destroy_pending = False  # type: ignore[attr-defined]
            logger.debug("event_bus_worker_stop_failed", exc_info=True)

    async def _ensure_queue(self) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            event_type = getattr(event, "event_type", None)
            if event_type is None:
                logger.warning("event_missing_type", extra={"event": repr(event)})
                continue
            for handler in self._handlers.get(event_type, []):
                try:
                    result = handler(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.exception(
                        "event_handler_failed",
                        extra={"event_type": event_type.value},
                    )
                    await self._invoke_handler_error_callback(event_type, exc, event)
            self._queue.task_done()

    async def _invoke_handler_error_callback(
        self,
        event_type: EventType,
        exc: Exception,
        event: Any,
    ) -> None:
        callback = self._on_handler_error
        if callback is None:
            return
        try:
            result = callback(event_type, exc, event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception(
                "event_handler_error_callback_failed",
                extra={"event_type": event_type.value},
            )

    async def drain(self) -> None:
        """Wait until all queued events have been processed."""
        await self._ensure_queue()
        assert self._queue is not None
        await self._queue.join()

    def reset(self) -> None:
        """Clear handlers and worker state (tests only)."""
        self._handlers.clear()
        self._stop_worker()


async def _await_cancelled_task(task: asyncio.Task[None]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        pass


_EVENT_BUS: EventBus | None = None
_DEFAULTS_INSTALLED = False


def stop_event_bus_worker() -> None:
    """Stop the cached bus worker without clearing handlers or singleton state."""
    if _EVENT_BUS is None:
        return
    _EVENT_BUS._stop_worker()


def stop_all_event_bus_workers() -> None:
    """Sync-stop every live EventBus (sessionfinish safety net for orphan locals)."""
    for bus in list(_ALL_BUSES):
        pending = bus._worker_task
        bus._stop_worker()
        if pending is not None and not pending.done():
            pending.cancel()
            pending._log_destroy_pending = False  # type: ignore[attr-defined]


async def astop_event_bus_worker() -> None:
    """Async stop for the process-wide bus (safe when stopping from the worker's loop)."""
    if _EVENT_BUS is None:
        return
    await _EVENT_BUS.astop_worker()


def on_event(event_type: EventType) -> Callable[[EventHandler], EventHandler]:
    """Decorator that registers a handler on the process-wide bus."""

    def decorator(handler: EventHandler) -> EventHandler:
        get_event_bus().subscribe(event_type, handler)
        return handler

    return decorator


def install_default_event_bus_hooks() -> None:
    """Wire process-wide bus safety nets (handler failure → extract_warnings)."""
    from backend.events.handler_errors import persist_event_handler_failure

    get_event_bus().set_handler_error_callback(persist_event_handler_failure)


def get_event_bus() -> EventBus:
    """Return the process-wide bus, installing official RAG defaults on first use."""
    global _EVENT_BUS, _DEFAULTS_INSTALLED

    if _EVENT_BUS is None:
        _EVENT_BUS = EventBus()
    if not _DEFAULTS_INSTALLED:
        # Mark installed before register/hooks so nested get_event_bus() is safe.
        _DEFAULTS_INSTALLED = True
        from backend.events.pipeline_finalized_handlers import register_pipeline_finalized_handlers

        register_pipeline_finalized_handlers()
        install_default_event_bus_hooks()
    return _EVENT_BUS


def reset_event_bus_cache() -> None:
    """Clear singleton bus state and reinstall official defaults (tests)."""
    global _EVENT_BUS, _DEFAULTS_INSTALLED

    if _EVENT_BUS is not None:
        _EVENT_BUS.reset()
        _EVENT_BUS._stop_worker()
    _EVENT_BUS = None
    _DEFAULTS_INSTALLED = False
    get_event_bus()
