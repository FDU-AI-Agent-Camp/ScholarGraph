# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""EventBus empty-subscriber early-exit (P13-R2 micro-opt)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from backend.events.bus import EventBus
from backend.events.types import EventType, RagIndexed
from backend.schemas.paper import PaperStatus


@pytest.mark.asyncio
async def test_publish_skips_queue_when_no_subscribers() -> None:
    bus = EventBus()
    assert bus._queue is None

    await bus.publish(
        RagIndexed(paper_id="p1", success=False, terminal_status=PaperStatus.READY_WITH_WARNINGS),
    )

    assert bus._queue is None
    assert bus._worker_task is None


def test_publish_sync_skips_cross_loop_hop_when_no_subscribers() -> None:
    bus = EventBus()
    with (
        patch("backend.events.bus.asyncio.run_coroutine_threadsafe") as threadsafe,
        patch("backend.events.bus.run_async") as run_async,
    ):
        bus.publish_sync(
            RagIndexed(paper_id="p1", success=False, terminal_status=PaperStatus.READY_WITH_WARNINGS),
        )

    threadsafe.assert_not_called()
    run_async.assert_not_called()


@pytest.mark.asyncio
async def test_publish_still_dispatches_when_subscriber_present() -> None:
    bus = EventBus()
    seen: list[RagIndexed] = []

    async def _capture(event: RagIndexed) -> None:
        seen.append(event)

    bus.subscribe(EventType.RAG_INDEXED, _capture)
    event = RagIndexed(paper_id="p2", success=True, terminal_status=PaperStatus.READY)
    await bus.publish(event)
    await bus.drain()

    assert seen == [event]
