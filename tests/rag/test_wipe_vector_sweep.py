# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Read-time soft isolation + Wave-2 wipe compensate for ghost vectors."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.rag.indexing_run_registry import get_indexing_run_registry
from backend.rag.models import PaperChunk
from backend.rag.vector_store import VectorStore
from backend.rag.wipe_vector_sweep import (
    extend_wipe_targets_after_abort,
    reset_wipe_sweep_tasks_for_tests,
    schedule_wipe_wave2_sweep,
    snapshot_wipe_target_run_ids,
)
from backend.schemas.paper import PaperStatus

from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service
from tests.rag.test_vector_store import FakeCollection, FakeEmbeddingClient


@pytest.fixture(autouse=True)
def _reset_wipe_tasks() -> None:
    from backend.repositories.vector_cleanup_queue_repository import (
        get_vector_cleanup_queue_repository,
        reset_vector_cleanup_queue_repository,
    )

    reset_wipe_sweep_tasks_for_tests()
    get_indexing_run_registry().reset()
    reset_vector_cleanup_queue_repository()
    try:
        get_vector_cleanup_queue_repository().clear_all_sync()
    except Exception:
        pass
    yield
    reset_wipe_sweep_tasks_for_tests()
    get_indexing_run_registry().reset()
    try:
        get_vector_cleanup_queue_repository().clear_all_sync()
    except Exception:
        pass
    reset_vector_cleanup_queue_repository()


def _chunk(paper_id: str, text: str, *, chunk_id: str = "c0") -> PaperChunk:
    return PaperChunk(
        chunk_id=chunk_id,
        paper_id=paper_id,
        text=text,
        section="body",
        chunk_index=0,
        source="pymupdf",
        char_start=0,
        char_end=len(text),
    )


@pytest.mark.asyncio
async def test_query_fail_closed_when_active_run_missing(persistence_env) -> None:
    """Orphan upserts without active pointer must not surface in QA / Patrol queries."""
    paper_id = "ghost-read-blind"
    await register_test_paper(paper_id, status=PaperStatus.READY)
    service = await restart_paper_service()

    chunk_col = FakeCollection()
    store = VectorStore(
        paper_service=service,
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=chunk_col,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )
    await store._index_chunks([_chunk(paper_id, "ghost body")], run_id="run_orphan")
    assert await service.get_active_run_id(paper_id) is None

    results = await store.query_chunks("ghost", paper_id=paper_id, top_k=5)
    assert results == []
    # Physical row still present until Wave-2 / delete_run.
    assert len(chunk_col.records) == 1


@pytest.mark.asyncio
async def test_wipe_wave2_delete_run_after_short_delay(persistence_env) -> None:
    """Wave 2 schedules delete_run for revoked ids so late ghosts are physically erased."""
    paper_id = "wipe-wave2"
    await register_test_paper(paper_id, status=PaperStatus.READY)
    service = await restart_paper_service()
    await service.set_active_run_id(paper_id, "run_old")
    get_indexing_run_registry().begin(paper_id, "run_inflight")

    targets = await snapshot_wipe_target_run_ids(paper_id)
    assert "run_old" in targets
    assert "run_inflight" in targets
    get_indexing_run_registry().revoke(paper_id, "run_inflight")
    targets = extend_wipe_targets_after_abort(paper_id, targets)
    assert "run_inflight" in targets

    delete_calls: list[tuple[str, str]] = []

    async def _fake_compensate(pid: str, rid: str, *, delays_seconds: tuple[float, ...] = ()) -> None:
        delete_calls.append((pid, rid))
        for delay in delays_seconds:
            if delay > 0:
                await asyncio.sleep(delay)

    with patch("backend.rag.handlers._compensate_revoked_index_run", _fake_compensate):
        tasks = schedule_wipe_wave2_sweep(
            paper_id,
            targets,
            delays_seconds=(0.01,),
        )
        assert len(tasks) == 2
        await asyncio.gather(*tasks)

    assert sorted(delete_calls) == sorted(
        [
            (paper_id, "run_inflight"),
            (paper_id, "run_old"),
        ]
    )


@pytest.mark.asyncio
async def test_force_delete_schedules_wave2_after_wave1(persistence_env, tmp_path: Path) -> None:
    """Production delete_paper wires Wave-1 purge then Wave-2 schedule for snapshotted runs."""
    from backend.services.paper_delete_service import get_paper_delete_service

    paper_id = "delete-two-wave"
    await register_test_paper(paper_id, status=PaperStatus.READY, pdf_path=str(tmp_path / f"{paper_id}.pdf"))
    (tmp_path / f"{paper_id}.pdf").write_bytes(b"%PDF-1.4")
    service = await restart_paper_service()
    await service.set_active_run_id(paper_id, "run_ready")
    delete_service = get_paper_delete_service()

    scheduled: list[tuple[str, set[str]]] = []

    def _capture_schedule(pid: str, run_ids: set[str], **_kwargs: object) -> list[object]:
        scheduled.append((pid, set(run_ids)))
        return []

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()

    with (
        patch(
            "backend.services.paper_delete_service.abort_in_flight_pipeline",
            AsyncMock(),
        ),
        patch(
            "backend.rag.wipe_vector_sweep.schedule_wipe_wave2_sweep",
            _capture_schedule,
        ),
        patch(
            "backend.rag.wipe_vector_sweep.snapshot_wipe_target_run_ids",
            new=AsyncMock(return_value={"run_ready"}),
        ),
        patch(
            "backend.rag.wipe_vector_sweep.extend_wipe_targets_after_abort",
            side_effect=lambda _pid, targets: targets,
        ),
    ):
        await delete_service.delete(paper_id, force=True, vector_store=vector_store)

    vector_store.delete_by_paper.assert_awaited_once_with(paper_id)
    assert scheduled == [(paper_id, {"run_ready"})]


@pytest.mark.asyncio
async def test_index_chunks_skips_without_run_id_on_run_aware_store() -> None:
    """Run-aware stores must not upsert Chroma rows lacking index_run_id metadata."""
    paper_service = MagicMock()
    paper_service.get_active_run_id = AsyncMock(return_value=None)
    chunk_col = FakeCollection()
    store = VectorStore(
        paper_service=paper_service,
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=chunk_col,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )
    await store._index_chunks([_chunk("p-skip", "no run")], run_id=None)
    assert chunk_col.records == {}
