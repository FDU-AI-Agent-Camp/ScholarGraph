"""Run async repository coroutines from synchronous LangGraph / service code.

The process-wide SQLAlchemy async engine must **not** be disposed from this
module. Connection pooling is tied to application lifespan; this bridge only
schedules coroutines onto an appropriate event loop.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")

_NESTED_BRIDGE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="async-bridge-nested")

_MAIN_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
_MAIN_LOOP_THREAD_ID: int | None = None

_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_BRIDGE_THREAD: threading.Thread | None = None
_BRIDGE_READY = threading.Event()
_BRIDGE_LOCK = threading.Lock()


def register_main_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Bind the long-lived application loop (FastAPI lifespan / uvicorn)."""
    global _MAIN_EVENT_LOOP, _MAIN_LOOP_THREAD_ID

    _MAIN_EVENT_LOOP = loop
    _MAIN_LOOP_THREAD_ID = threading.get_ident() if loop is not None else None


def get_registered_main_event_loop() -> asyncio.AbstractEventLoop | None:
    """Return the application loop registered by ``register_main_event_loop``."""
    return _MAIN_EVENT_LOOP


def get_registered_main_loop_thread_id() -> int | None:
    """Return the thread id that registered the application loop, if any."""
    return _MAIN_LOOP_THREAD_ID


def _bridge_thread_main() -> None:
    global _BRIDGE_LOOP

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _BRIDGE_LOOP = loop
    _BRIDGE_READY.set()
    loop.run_forever()


def _ensure_bridge_loop() -> asyncio.AbstractEventLoop:
    global _BRIDGE_THREAD

    with _BRIDGE_LOCK:
        if _BRIDGE_LOOP is not None and _BRIDGE_LOOP.is_running():
            return _BRIDGE_LOOP

        _BRIDGE_READY.clear()
        _BRIDGE_THREAD = threading.Thread(
            target=_bridge_thread_main,
            name="async-bridge-loop",
            daemon=True,
        )
        _BRIDGE_THREAD.start()

    if not _BRIDGE_READY.wait(timeout=10):
        msg = "async bridge loop failed to start within 10 seconds"
        raise RuntimeError(msg)
    assert _BRIDGE_LOOP is not None
    return _BRIDGE_LOOP


def _run_on_bridge_loop(coro: Coroutine[object, object, T]) -> T:
    loop = _ensure_bridge_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def _run_nested_from_bridge_loop(coro: Coroutine[object, object, T]) -> T:
    """Run a nested sync bridge call from a coroutine already executing on the bridge loop."""
    return _NESTED_BRIDGE_EXECUTOR.submit(asyncio.run, coro).result()


async def _dispose_cached_engine() -> None:
    from backend.db.base import get_async_engine

    if not get_async_engine.cache_info().currsize:
        return
    await get_async_engine().dispose()


def dispose_cached_engine_if_present() -> None:
    """Dispose the cached async engine on the bridge loop (tests / env reset)."""
    from backend.db.base import get_async_engine

    if not get_async_engine.cache_info().currsize:
        return
    try:
        _run_on_bridge_loop(_dispose_cached_engine())
    except Exception:
        pass


def run_async(coro: Coroutine[object, object, T]) -> T:
    """Execute a coroutine from sync callers, including inside a running event loop."""
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is None:
        main_loop = _MAIN_EVENT_LOOP
        if main_loop is not None and main_loop.is_running() and threading.get_ident() != _MAIN_LOOP_THREAD_ID:
            return asyncio.run_coroutine_threadsafe(coro, main_loop).result()
        return _run_on_bridge_loop(coro)

    if running_loop is _BRIDGE_LOOP:
        return _run_nested_from_bridge_loop(coro)

    # Running loop on this thread: schedule on the persistent bridge loop.
    return _run_on_bridge_loop(coro)
