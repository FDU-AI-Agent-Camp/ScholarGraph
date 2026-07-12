"""Run async repository coroutines from synchronous LangGraph / service code."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")


def _dispose_engine(loop: asyncio.AbstractEventLoop) -> None:
    from backend.db.base import get_async_engine

    if not get_async_engine.cache_info().currsize:
        return
    try:
        loop.run_until_complete(get_async_engine().dispose())
    except Exception:
        pass
    get_async_engine.cache_clear()
    from backend.db.base import get_async_session_factory

    get_async_session_factory.cache_clear()


def _run_in_fresh_loop(coro: Coroutine[object, object, T]) -> T:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        _dispose_engine(loop)
        loop.close()


def run_async(coro: Coroutine[object, object, T]) -> T:
    """Execute a coroutine from sync callers, including inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run_in_fresh_loop(coro)

    result: list[T] = []
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            result.append(_run_in_fresh_loop(coro))
        except BaseException as exc:  # noqa: BLE001 — propagate to caller thread
            error.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]
