"""Lightweight in-process event bus for cross-module decoupling."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from backend.events.types import EventType
from backend.repositories.async_bridge import run_async

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Awaitable[None] | None]


class EventBus:
    """Minimal pub/sub bus backed by an asyncio queue."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[Any] | None = None
        self._worker_task: asyncio.Task[None] | None = None

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        await self._ensure_queue()
        assert self._queue is not None
        await self._queue.put(event)

    def publish_sync(self, event: Any) -> None:
        """Publish from synchronous callers (e.g. pipeline finalize)."""

        async def _publish_and_drain() -> None:
            await self.publish(event)
            await self.drain()
            self._stop_worker()

        run_async(_publish_and_drain())

    def _stop_worker(self) -> None:
        """Tear down the background worker after a sync publish cycle."""
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
                except Exception:
                    logger.exception(
                        "event_handler_failed",
                        extra={"event_type": event_type.value},
                    )
            self._queue.task_done()

    async def drain(self) -> None:
        """Wait until queued events are processed (tests only)."""
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


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus()


def reset_event_bus_cache() -> None:
    if get_event_bus.cache_info().currsize:
        get_event_bus().reset()
    get_event_bus.cache_clear()
