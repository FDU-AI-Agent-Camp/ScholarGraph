"""Lightweight in-process event bus for cross-module decoupling."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from backend.events.types import EventType
from backend.repositories.async_bridge import run_async

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Awaitable[None] | None]
HandlerErrorCallback = Callable[[EventType, Exception, Any], Awaitable[None] | None]


class EventBus:
    """Minimal pub/sub bus backed by an asyncio queue."""

    def __init__(self, *, on_handler_error: HandlerErrorCallback | None = None) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[Any] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._on_handler_error = on_handler_error

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

        from backend.repositories import async_bridge

        main_loop = async_bridge._MAIN_EVENT_LOOP
        main_loop_thread_id = async_bridge._MAIN_LOOP_THREAD_ID
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

    def _stop_worker(self) -> None:
        """Tear down the background worker (tests / application shutdown)."""
        if self._worker_task is not None and not self._worker_task.done():
            self._worker_task.cancel()
        self._worker_task = None
        self._queue = None

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


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus()


def reset_event_bus_cache() -> None:
    if get_event_bus.cache_info().currsize:
        get_event_bus().reset()
    get_event_bus.cache_clear()
    from backend.events.pipeline_finalized_handlers import register_pipeline_finalized_handlers

    register_pipeline_finalized_handlers()
    install_default_event_bus_hooks()
