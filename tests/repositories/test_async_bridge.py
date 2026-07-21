# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for sync/async repository bridge (U-BRG-01/02)."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from backend.db.base import get_async_engine
from backend.repositories.async_bridge import register_main_event_loop, run_async
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.pipeline_status_service import get_pipeline_status_service
from sqlalchemy import event
from tests.helpers.persistence_testkit import register_test_paper

POOL_BURST_WRITE_COUNT = 40
MAX_EXPECTED_PHYSICAL_CONNECTS = 5
CONCURRENT_WRITER_THREADS = 12
CONCURRENT_WRITES_PER_THREAD = 5


@pytest.mark.asyncio
async def test_run_async_from_running_loop_returns_value() -> None:
    async def compute() -> int:
        await asyncio.sleep(0)
        return 42

    assert run_async(compute()) == 42


def test_run_async_without_running_loop_returns_value() -> None:
    async def compute() -> str:
        return "ok"

    assert run_async(compute()) == "ok"


@pytest.mark.asyncio
async def test_run_async_preserves_cached_engine_across_calls(persistence_env) -> None:
    async def touch_engine() -> int:
        engine = get_async_engine()
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return 1

    assert get_async_engine.cache_info().currsize == 1
    assert run_async(touch_engine()) == 1
    assert get_async_engine.cache_info().currsize == 1
    assert run_async(touch_engine()) == 1
    assert get_async_engine.cache_info().currsize == 1


def test_run_async_from_worker_thread_uses_registered_main_loop() -> None:
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    errors: list[BaseException] = []

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        register_main_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    ready.wait(timeout=5)

    async def compute() -> int:
        return 99

    try:
        assert run_async(compute()) == 99
    except BaseException as exc:  # noqa: BLE001 — capture for finally
        errors.append(exc)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        register_main_event_loop(None)
        loop.close()

    assert errors == []


def test_run_async_reuses_sqlalchemy_pool_for_burst_writes(persistence_env) -> None:
    paper_id = "pool-reuse-bridge"
    run_async(register_test_paper(paper_id, status=PaperStatus.PROCESSING))

    engine = get_async_engine()
    physical_connects = 0

    def _count_connect(_dbapi_connection: object, _connection_record: object) -> None:
        nonlocal physical_connects
        physical_connects += 1

    event.listen(engine.sync_engine, "connect", _count_connect)
    status_service = get_pipeline_status_service()
    processing_stages = (
        PipelineStage.INGESTING,
        PipelineStage.HEAD_REFINING,
        PipelineStage.CLASSIFYING,
        PipelineStage.EXTRACTING,
        PipelineStage.STORING,
    )

    try:
        for index in range(POOL_BURST_WRITE_COUNT):
            stage = processing_stages[index % len(processing_stages)]
            run_async(status_service.advance_stage(paper_id, stage, message=f"burst-{index}"))
    finally:
        event.remove(engine.sync_engine, "connect", _count_connect)

    assert physical_connects <= MAX_EXPECTED_PHYSICAL_CONNECTS


def test_run_async_concurrent_threads_pipeline_writes(persistence_env) -> None:
    paper_id = "concurrent-bridge-writes"
    run_async(register_test_paper(paper_id, status=PaperStatus.PROCESSING))
    status_service = get_pipeline_status_service()
    processing_stages = (
        PipelineStage.INGESTING,
        PipelineStage.CLASSIFYING,
        PipelineStage.EXTRACTING,
        PipelineStage.STORING,
    )

    def write_batch(thread_id: int) -> int:
        for offset in range(CONCURRENT_WRITES_PER_THREAD):
            stage = processing_stages[(thread_id + offset) % len(processing_stages)]
            run_async(
                status_service.advance_stage(
                    paper_id,
                    stage,
                    message=f"thread-{thread_id}-write-{offset}",
                )
            )
        return thread_id

    with ThreadPoolExecutor(max_workers=CONCURRENT_WRITER_THREADS) as pool:
        futures = [pool.submit(write_batch, thread_id) for thread_id in range(CONCURRENT_WRITER_THREADS)]
        completed = [future.result(timeout=30) for future in as_completed(futures)]

    assert len(completed) == CONCURRENT_WRITER_THREADS
    assert len(set(completed)) == CONCURRENT_WRITER_THREADS


def test_run_async_nested_calls_from_bridge_loop_do_not_deadlock(persistence_env) -> None:
    paper_id = "nested-bridge-calls"
    run_async(register_test_paper(paper_id, status=PaperStatus.PROCESSING))

    from backend.services.paper_service import get_paper_service

    detail = run_async(get_paper_service().get_paper(paper_id))
    assert detail.paper_id == paper_id
