# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""D10 boundary tests: latency isolation and concurrent publish_sync stress."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import TYPE_CHECKING

import pytest
from backend.events import pipeline_finalized_handlers as handler_module
from backend.events.bus import get_event_bus
from backend.events.types import EventType, PipelineFinalized
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import complete_paper_pipeline
from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service

if TYPE_CHECKING:
    from pathlib import Path

SLOW_HANDLER_DELAY_SECONDS = 5.0
MAX_COMPLETE_PIPELINE_SECONDS = 2.0
CONCURRENT_PUBLISH_THREAD_COUNT = 10
CONCURRENCY_DRAIN_TIMEOUT_SECONDS = 30.0


def _minimal_graph(paper_id: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="boundary node", type="Method")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="REF",
                type="REF",
            ),
        ],
    )


def _sample_classification() -> ParadigmClassification:
    return ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.91,
        reason="D10 boundary classification",
    )


@pytest.mark.asyncio
async def test_complete_paper_pipeline_latency_isolated_from_slow_rag_handler(
    persistence_env: dict[str, Path],
) -> None:
    """Latency isolation: finalize must return before a 5s background handler completes."""
    paper_id = "d10-latency-isolation"
    await register_test_paper(paper_id, title="D10 latency isolation")
    await restart_paper_service()
    paper_service = get_paper_service()

    graph = _minimal_graph(paper_id)
    graph_path = str(persistence_env["graph_dir"] / f"{paper_id}.json")

    handler_module.unregister_pipeline_finalized_handlers()
    bus = get_event_bus()

    async def slow_rag_handler(_event: PipelineFinalized) -> None:
        await asyncio.sleep(SLOW_HANDLER_DELAY_SECONDS)

    bus.subscribe(EventType.PIPELINE_FINALIZED, slow_rag_handler)

    try:
        started = time.perf_counter()
        complete_paper_pipeline(
            paper_service,
            paper_id,
            classification=_sample_classification(),
            graph=graph,
            graph_path=graph_path,
            full_text="latency isolation full text body",
        )
        elapsed = time.perf_counter() - started

        assert elapsed < MAX_COMPLETE_PIPELINE_SECONDS, (
            f"complete_paper_pipeline blocked for {elapsed:.3f}s; "
            f"fire-and-forget must finish well under {SLOW_HANDLER_DELAY_SECONDS:.0f}s "
            f"(budget {MAX_COMPLETE_PIPELINE_SECONDS:.1f}s including DB writes)"
        )
    finally:
        bus.reset()
        handler_module.register_pipeline_finalized_handlers(force=True)


def test_publish_sync_concurrent_interleaved_publish_all_consumed() -> None:
    """Concurrency stress: 10 threads interleave publish_sync on the global singleton bus."""
    handler_module.unregister_pipeline_finalized_handlers()
    bus = get_event_bus()
    bus.reset()

    lock = threading.Lock()
    consumed: list[str] = []

    async def capture(event: PipelineFinalized) -> None:
        with lock:
            consumed.append(event.paper_id)

    bus.subscribe(EventType.PIPELINE_FINALIZED, capture)

    def publish_one(index: int) -> None:
        paper_id = f"d10-concurrent-{index:02d}"
        bus.publish_sync(
            PipelineFinalized(
                paper_id=paper_id,
                full_text=f"concurrent body {index}",
                graph=_minimal_graph(paper_id),
            )
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_PUBLISH_THREAD_COUNT) as executor:
            futures = [executor.submit(publish_one, index) for index in range(CONCURRENT_PUBLISH_THREAD_COUNT)]
            for future in futures:
                future.result(timeout=CONCURRENCY_DRAIN_TIMEOUT_SECONDS)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as drain_executor:
            drain_future = drain_executor.submit(bus.drain_sync)
            drain_future.result(timeout=CONCURRENCY_DRAIN_TIMEOUT_SECONDS)

        expected_ids = {f"d10-concurrent-{index:02d}" for index in range(CONCURRENT_PUBLISH_THREAD_COUNT)}
        assert set(consumed) == expected_ids
        assert len(consumed) == CONCURRENT_PUBLISH_THREAD_COUNT
    finally:
        bus.reset()
        handler_module.register_pipeline_finalized_handlers(force=True)
