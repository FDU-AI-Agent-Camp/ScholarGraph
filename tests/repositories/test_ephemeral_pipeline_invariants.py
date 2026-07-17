# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Deep serialization, concurrency, and invariant tests for D6 ephemeral pipeline state."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pytest
from backend.db.base import get_async_session_factory
from backend.db.models import PipelineRunRow
from backend.repositories.async_bridge import run_async
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService, get_paper_service
from sqlalchemy.orm.attributes import flag_modified
from tests.helpers.persistence_testkit import (
    register_test_paper,
    restart_paper_service,
    simulate_service_crash,
)

STRESS_NODE_COUNT = 2500
CONCURRENT_WRITE_ITERATIONS = 80
CONCURRENT_READ_ITERATIONS = 120
CONCURRENT_READER_THREADS = 6
CONCURRENT_WRITER_THREADS = 4

_SPECIAL_LABEL_FRAGMENT = "引号\"测试'\n🧪\\slash\t制表符"
_LONG_DATA_CHARS = 48_000


def _sample_preview(paper_id: str, *, label: str = "Preview Thesis") -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(
                id="n_root",
                label=label,
                type="Thesis",
                data={"level1": {"level2": {"level3": {"anchor": "original"}}}},
            ),
            GraphNode(id="n_sub", label="Sub", type="SubArgument"),
        ],
        edges=[
            GraphEdge(
                id="e_sub",
                source="n_sub",
                target="n_root",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
        ],
    )


def _build_stress_topology(paper_id: str) -> UnifiedPaperGraph:
    """Large cyclic STEM graph with special characters and oversized payload fields."""
    nodes = [
        GraphNode(
            id=f"n{i}",
            label=f"{_SPECIAL_LABEL_FRAGMENT}-{i}",
            type="Claim",
            data={
                "blob": "α" * _LONG_DATA_CHARS,
                "meta": {"index": i, "tags": ["stress", "unicode", "🧪"]},
            },
        )
        for i in range(STRESS_NODE_COUNT)
    ]
    edges = [
        GraphEdge(
            id=f"e{i}",
            source=f"n{i}",
            target=f"n{(i + 1) % STRESS_NODE_COUNT}",
            label="RELATES_TO",
            type="RELATES_TO",
        )
        for i in range(STRESS_NODE_COUNT)
    ]
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.STEM,
        nodes=nodes,
        edges=edges,
        summary="stress topology " + _SPECIAL_LABEL_FRAGMENT,
    )


@pytest.mark.asyncio
async def test_preview_graph_inplace_mutation_not_persisted_without_flag_modified(
    persistence_env,
) -> None:
    """SQLAlchemy JSON columns do not track in-place nested dict edits."""
    paper_id = "json-mutation-no-flag"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    repo = PipelineRepository()
    await repo.save_preview_graph(paper_id, _sample_preview(paper_id))

    async with get_async_session_factory()() as session:
        from backend.repositories.pipeline_repository import PipelineRepository as Repo

        await Repo()._begin_immediate(session)
        run = await session.get(PipelineRunRow, paper_id)
        assert run is not None and run.preview_graph is not None
        run.preview_graph["nodes"][0]["label"] = "MUTATED_IN_PLACE"
        run.preview_graph["nodes"][0]["data"]["level1"]["level2"]["level3"]["anchor"] = "deep-edit"
        await session.commit()

    reloaded = await repo.get_preview_graph(paper_id)
    assert reloaded is not None
    assert reloaded.nodes[0].label == "Preview Thesis"
    assert reloaded.nodes[0].data["level1"]["level2"]["level3"]["anchor"] == "original"


@pytest.mark.asyncio
async def test_preview_graph_inplace_mutation_persisted_with_flag_modified(
    persistence_env,
) -> None:
    """``flag_modified`` is required when mutating JSON columns in place."""
    paper_id = "json-mutation-with-flag"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    repo = PipelineRepository()
    await repo.save_preview_graph(paper_id, _sample_preview(paper_id))

    async with get_async_session_factory()() as session:
        from backend.repositories.pipeline_repository import PipelineRepository as Repo

        await Repo()._begin_immediate(session)
        run = await session.get(PipelineRunRow, paper_id)
        assert run is not None and run.preview_graph is not None
        run.preview_graph["nodes"][0]["label"] = "MUTATED_WITH_FLAG"
        run.preview_graph["nodes"][0]["data"]["level1"]["level2"]["level3"]["anchor"] = "deep-flag"
        flag_modified(run, "preview_graph")
        await session.commit()

    reloaded = await repo.get_preview_graph(paper_id)
    assert reloaded is not None
    assert reloaded.nodes[0].label == "MUTATED_WITH_FLAG"
    assert reloaded.nodes[0].data["level1"]["level2"]["level3"]["anchor"] == "deep-flag"


@pytest.mark.asyncio
async def test_save_preview_graph_replaces_payload_atomically(persistence_env) -> None:
    """Production path assigns a fresh dict — deep fields survive round-trip."""
    paper_id = "json-full-replace"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    repo = PipelineRepository()
    original = _sample_preview(paper_id, label="Atomic Replace")
    await repo.save_preview_graph(paper_id, original)

    updated = original.model_copy(
        update={
            "nodes": [
                original.nodes[0].model_copy(
                    update={
                        "label": "Replaced Root",
                        "data": {"level1": {"level2": {"level3": {"anchor": "replaced"}}}},
                    },
                ),
                original.nodes[1],
            ],
        },
    )
    await repo.save_preview_graph(paper_id, updated)

    reloaded = await repo.get_preview_graph(paper_id)
    assert reloaded is not None
    assert reloaded.nodes[0].label == "Replaced Root"
    assert reloaded.nodes[0].data["level1"]["level2"]["level3"]["anchor"] == "replaced"


@pytest.mark.asyncio
async def test_preview_graph_extreme_topology_survives_restart(persistence_env) -> None:
    """Heavy JSON payload round-trips without truncation or decode failure."""
    paper_id = "json-stress-topology"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    stress_graph = _build_stress_topology(paper_id)

    service = PaperService()
    service.save_preview_graph(paper_id, stress_graph)
    service.set_active_run_id(paper_id, "run-stress-topology")

    simulate_service_crash()
    restarted = await restart_paper_service()

    loaded = restarted.get_preview_graph(paper_id)
    assert loaded is not None
    assert len(loaded.nodes) == STRESS_NODE_COUNT
    assert len(loaded.edges) == STRESS_NODE_COUNT
    assert loaded.nodes[0].label.startswith(_SPECIAL_LABEL_FRAGMENT)
    assert len(loaded.nodes[0].data["blob"]) == _LONG_DATA_CHARS
    assert loaded.nodes[STRESS_NODE_COUNT - 1].id == f"n{STRESS_NODE_COUNT - 1}"
    assert restarted.get_active_run_id(paper_id) == "run-stress-topology"


@pytest.mark.asyncio
async def test_active_run_id_visibility_follows_committed_writes(persistence_env) -> None:
    """Readers observe run_id changes only after writer commits."""
    paper_id = "run-id-visibility"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    repo = PipelineRepository()
    service = get_paper_service()

    service.set_active_run_id(paper_id, "run-v1")
    assert service.get_active_run_id(paper_id) == "run-v1"
    assert await repo.get_active_rag_run_id(paper_id) == "run-v1"

    service.set_active_run_id(paper_id, "run-v2")
    assert service.get_active_run_id(paper_id) == "run-v2"

    service.set_active_run_id(paper_id, None)
    assert service.get_active_run_id(paper_id) is None


def test_active_run_id_reads_nonblocking_under_concurrent_pipeline_writes(
    persistence_env,
) -> None:
    """WAL readers must not raise ``database is locked`` while writers hold IMMEDIATE locks."""
    paper_id = "run-id-concurrency"
    run_async(register_test_paper(paper_id, status=PaperStatus.PROCESSING))
    pipeline_repo = PipelineRepository()
    service = get_paper_service()
    now = datetime.now(UTC)
    reader_errors: list[str] = []
    observed_run_ids: list[str | None] = []
    stop = threading.Event()

    def _writer_loop() -> None:
        stages = (
            PipelineStage.INGESTING,
            PipelineStage.HEAD_REFINING,
            PipelineStage.CLASSIFYING,
            PipelineStage.EXTRACTING,
            PipelineStage.STORING,
        )
        for index in range(CONCURRENT_WRITE_ITERATIONS):
            if stop.is_set():
                return
            stage = stages[index % len(stages)]
            snapshot = PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.PROCESSING,
                percent=min(95, (index + 1) % 100),
                stage=stage,
                message=f"writer-{index}",
                updated_at=now,
            )
            run_async(pipeline_repo.save_status(paper_id, snapshot))
            if index % 7 == 0:
                run_async(
                    pipeline_repo.set_active_rag_run_id(
                        paper_id,
                        f"run-{index // 7}",
                    ),
                )

    def _reader_loop() -> None:
        while not stop.is_set():
            try:
                observed_run_ids.append(service.get_active_run_id(paper_id))
            except Exception as exc:  # noqa: BLE001 — collect concurrency faults
                reader_errors.append(str(exc))

    writers = [
        threading.Thread(target=_writer_loop, name=f"writer-{idx}", daemon=True)
        for idx in range(CONCURRENT_WRITER_THREADS)
    ]
    readers = [
        threading.Thread(target=_reader_loop, name=f"reader-{idx}", daemon=True)
        for idx in range(CONCURRENT_READER_THREADS)
    ]

    for thread in [*writers, *readers]:
        thread.start()

    time.sleep(1.5)
    stop.set()
    for thread in [*writers, *readers]:
        thread.join(timeout=10)

    locked_errors = [msg for msg in reader_errors if "database is locked" in msg.lower()]
    assert locked_errors == []
    assert reader_errors == []
    assert observed_run_ids


def test_active_run_id_concurrent_read_write_threads_complete(persistence_env) -> None:
    """Mixed read/write thread pool completes without SQLite lock errors."""
    paper_id = "run-id-mixed-pool"
    run_async(register_test_paper(paper_id, status=PaperStatus.PROCESSING))
    repo = PipelineRepository()
    service = get_paper_service()
    now = datetime.now(UTC)
    errors: list[str] = []

    def _mixed_task(task_id: int) -> str:
        try:
            if task_id % 3 == 0:
                run_async(
                    repo.set_active_rag_run_id(paper_id, f"pool-run-{task_id}"),
                )
            elif task_id % 3 == 1:
                run_async(
                    repo.save_status(
                        paper_id,
                        PaperStatusData(
                            paper_id=paper_id,
                            status=PaperStatus.PROCESSING,
                            percent=task_id % 100,
                            stage=PipelineStage.EXTRACTING,
                            message=f"pool-{task_id}",
                            updated_at=now,
                        ),
                    ),
                )
            else:
                service.get_active_run_id(paper_id)
            return "ok"
        except Exception as exc:  # noqa: BLE001 — surface lock/contention issues
            errors.append(str(exc))
            return "error"

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_mixed_task, task_id) for task_id in range(CONCURRENT_READ_ITERATIONS)]
        results = [future.result(timeout=30) for future in as_completed(futures)]

    assert len(results) == CONCURRENT_READ_ITERATIONS
    locked_errors = [msg for msg in errors if "database is locked" in msg.lower()]
    assert locked_errors == []
    assert errors == []
