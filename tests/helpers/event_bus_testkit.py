# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Test helpers for the in-process EventBus."""

from __future__ import annotations

import asyncio

from backend.events.bus import get_event_bus


async def drain_event_bus() -> None:
    """Wait until all queued events on the process-wide bus are processed."""
    await asyncio.sleep(0)
    await asyncio.to_thread(get_event_bus().drain_sync)


def drain_event_bus_sync() -> None:
    """Drain the process-wide bus from synchronous test code."""
    get_event_bus().drain_sync()
