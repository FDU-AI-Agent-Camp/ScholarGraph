# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Dynamic trajectory audit: PaperService hot paths stay on the main event loop."""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from backend.debug import async_hotpath_audit
from backend.events.bus import get_event_bus
from backend.events.types import EventType, PipelineFinalized
from backend.repositories.async_bridge import register_main_event_loop, run_async
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import complete_paper_pipeline
from backend.services.status_snapshot_guard import persist_status_snapshot

from tests.helpers.persistence_testkit import register_test_paper


@pytest.fixture
def hotpath_audit() -> Any:
    async_hotpath_audit.enable()
    async_hotpath_audit.clear()
    yield
    async_hotpath_audit.disable()
    async_hotpath_audit.clear()


def _assert_all_on_main_loop(*, main_thread_id: int, main_loop_id: int) -> None:
    records = async_hotpath_audit.records()
    assert records, "expected at least one hot-path audit record"
    for entry in records:
        assert entry.thread_id == main_thread_id, (
            f"{entry.site} ran on thread {entry.thread_id} ({entry.thread_name!r}), "
            f"expected main thread {main_thread_id}"
        )
        assert entry.loop_id == main_loop_id, (
            f"{entry.site} ran on loop {entry.loop_id}, expected main loop {main_loop_id}"
        )
    assert async_hotpath_audit.bridge_crossings() == [], (
        f"async-bridge loop was used during hot-path audit: {async_hotpath_audit.bridge_crossings()!r}"
    )


@pytest.mark.asyncio
async def test_set_active_run_id_stays_on_main_loop(
    persistence_env,
    hotpath_audit,
) -> None:
    register_main_event_loop(asyncio.get_running_loop())
    main_thread_id = threading.get_ident()
    main_loop_id = id(asyncio.get_running_loop())

    paper_id = "hotpath-active-run"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = get_paper_service()
    await service.set_active_run_id(paper_id, "run-hotpath-001")

    sites = {entry.site for entry in async_hotpath_audit.records()}
    assert "paper_service.set_active_run_id" in sites
    _assert_all_on_main_loop(main_thread_id=main_thread_id, main_loop_id=main_loop_id)


@pytest.mark.asyncio
async def test_persist_status_snapshot_stays_on_main_loop(
    persistence_env,
    hotpath_audit,
) -> None:
    register_main_event_loop(asyncio.get_running_loop())
    main_thread_id = threading.get_ident()
    main_loop_id = id(asyncio.get_running_loop())

    from backend.graph.state import STAGE_PERCENT
    from backend.schemas.paper import PipelineStage
    from backend.services.pipeline_status_service import DEFAULT_STAGE_MESSAGES

    paper_id = "hotpath-snapshot"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = get_paper_service()
    await persist_status_snapshot(
        service,
        paper_id,
        status=PaperStatus.INDEXING,
        stage=PipelineStage.INDEXING,
        percent=STAGE_PERCENT[PipelineStage.INDEXING],
        message=DEFAULT_STAGE_MESSAGES[PipelineStage.INDEXING],
    )

    sites = {entry.site for entry in async_hotpath_audit.records()}
    assert "status_snapshot_guard.persist_status_snapshot" in sites
    _assert_all_on_main_loop(main_thread_id=main_thread_id, main_loop_id=main_loop_id)


@pytest.mark.asyncio
async def test_complete_paper_pipeline_persist_stays_on_main_loop(
    persistence_env,
    hotpath_audit,
) -> None:
    register_main_event_loop(asyncio.get_running_loop())
    main_thread_id = threading.get_ident()
    main_loop_id = id(asyncio.get_running_loop())

    paper_id = "hotpath-finalize"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = get_paper_service()
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="Method", type="Method")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="Hot-path audit edge with explicit rationale text.",
            ),
        ],
    )
    classification = ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="audit")

    with patch("backend.events.bus.get_event_bus") as mock_bus_factory:
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        mock_bus_factory.return_value = mock_bus
        await complete_paper_pipeline(
            service,
            paper_id,
            classification=classification,
            graph=graph,
            graph_path=str(persistence_env["graph_dir"] / f"{paper_id}.json"),
            full_text="hotpath finalize text",
        )

    sites = {entry.site for entry in async_hotpath_audit.records()}
    assert "status_snapshot_guard.persist_status_snapshot" in sites
    _assert_all_on_main_loop(main_thread_id=main_thread_id, main_loop_id=main_loop_id)


@pytest.mark.asyncio
async def test_eventbus_handler_set_active_run_id_stays_on_main_loop(
    persistence_env,
    hotpath_audit,
) -> None:
    register_main_event_loop(asyncio.get_running_loop())
    main_thread_id = threading.get_ident()
    main_loop_id = id(asyncio.get_running_loop())

    paper_id = "hotpath-eventbus"
    await register_test_paper(paper_id, status=PaperStatus.INDEXING)
    service = get_paper_service()
    bus = get_event_bus()

    async def _handler(_event: PipelineFinalized) -> None:
        await service.set_active_run_id(paper_id, "run-from-eventbus")

    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="Method", type="Method")],
        edges=[
            GraphEdge(
                id="e1",
                source="n1",
                target="n1",
                label="SUPPORTS",
                type="SUPPORTS",
                rationale="EventBus hot-path audit edge.",
            ),
        ],
    )
    bus.subscribe(EventType.PIPELINE_FINALIZED, _handler)
    await bus.publish(
        PipelineFinalized(
            paper_id=paper_id,
            full_text="eventbus hotpath",
            graph=graph,
        ),
    )
    await bus.drain()

    sites = {entry.site for entry in async_hotpath_audit.records()}
    assert "paper_service.set_active_run_id" in sites
    _assert_all_on_main_loop(main_thread_id=main_thread_id, main_loop_id=main_loop_id)


@pytest.mark.asyncio
async def test_rag_orphan_cleanup_set_active_run_id_stays_on_main_loop(
    persistence_env,
    hotpath_audit,
) -> None:
    """RAG compensate path must await PaperService on the same loop (no bridge)."""
    from unittest.mock import patch

    register_main_event_loop(asyncio.get_running_loop())
    main_thread_id = threading.get_ident()
    main_loop_id = id(asyncio.get_running_loop())

    paper_id = "hotpath-rag-cleanup"
    run_id = "run-orphan-audit"
    await register_test_paper(paper_id, status=PaperStatus.INDEXING)
    service = get_paper_service()
    await service.set_active_run_id(paper_id, run_id)
    async_hotpath_audit.clear()

    with patch("backend.rag.handlers.VectorStore") as store_cls:
        store_cls.return_value.delete_run = AsyncMock()
        from backend.rag.handlers import _compensate_revoked_index_run

        await _compensate_revoked_index_run(paper_id, run_id, delays_seconds=(0,))

    sites = {entry.site for entry in async_hotpath_audit.records()}
    assert "paper_service.set_active_run_id" in sites
    _assert_all_on_main_loop(main_thread_id=main_thread_id, main_loop_id=main_loop_id)


def test_bridge_hook_records_sync_run_async_crossing(hotpath_audit) -> None:
    """Negative control: sync ``run_async`` must trip the bridge audit hook."""

    async def _noop() -> None:
        return None

    assert run_async(_noop()) is None
    assert len(async_hotpath_audit.bridge_crossings()) >= 1
