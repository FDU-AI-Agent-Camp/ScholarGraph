# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Optional async hot-path audit: thread / loop identity + bridge crossings.

Enable via ``SCHOLARGRAPH_ASYNC_HOTPATH_AUDIT=1`` or :func:`enable` in tests.
When disabled, :func:`record` is a no-op (zero overhead on production paths).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ENV_FLAG = "SCHOLARGRAPH_ASYNC_HOTPATH_AUDIT"
_enabled = os.environ.get(_ENV_FLAG) == "1"
_records: list[HotpathRecord] = []
_bridge_crossings: list[BridgeCrossingRecord] = []


@dataclass(frozen=True, slots=True)
class HotpathRecord:
    site: str
    thread_id: int
    thread_name: str
    loop_id: int


@dataclass(frozen=True, slots=True)
class BridgeCrossingRecord:
    thread_id: int
    thread_name: str
    loop_id: int | None


def is_enabled() -> bool:
    return _enabled


def enable() -> None:
    global _enabled
    _enabled = True


def disable() -> None:
    global _enabled
    _enabled = False


def clear() -> None:
    _records.clear()
    _bridge_crossings.clear()


def records() -> list[HotpathRecord]:
    return list(_records)


def bridge_crossings() -> list[BridgeCrossingRecord]:
    return list(_bridge_crossings)


def record(site: str) -> None:
    """Capture current thread + running loop for a PaperService / snapshot hot path."""
    if not _enabled:
        return
    loop = asyncio.get_running_loop()
    thread_id = threading.get_ident()
    thread_name = threading.current_thread().name
    loop_id = id(loop)
    entry = HotpathRecord(
        site=site,
        thread_id=thread_id,
        thread_name=thread_name,
        loop_id=loop_id,
    )
    _records.append(entry)
    logger.info(
        "async_hotpath_audit site=%s thread_id=%s thread_name=%s loop_id=%s",
        site,
        thread_id,
        thread_name,
        loop_id,
    )


def record_bridge_crossing() -> None:
    """Record a ``_run_on_bridge_loop`` dispatch (should not happen on async hot paths)."""
    if not _enabled:
        return
    thread_id = threading.get_ident()
    thread_name = threading.current_thread().name
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    entry = BridgeCrossingRecord(
        thread_id=thread_id,
        thread_name=thread_name,
        loop_id=loop_id,
    )
    _bridge_crossings.append(entry)
    logger.warning(
        "async_hotpath_audit bridge_crossing thread_id=%s thread_name=%s loop_id=%s",
        thread_id,
        thread_name,
        loop_id,
    )
