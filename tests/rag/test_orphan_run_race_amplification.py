# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Race-amplification: timed-out Run A must not clobber successor Run B (P13 Problem 1).

Timeline (wall clock):
  t≈0.0s  Run A starts replace; chroma.upsert held by LatencyGate (~2s)
  t≈1.0s  wait_for → TimeoutError → revoke + compensating cleanup schedule
  t≈1.1s  Run B replace succeeds → READY + active_run_id=run_b
  t≈2.0s  Release Run A zombie thread → late upsert may write orphan chunks
  t>2.0s  Compensating delete_run erases Run A; status/active stay on Run B

``asyncio.wait_for`` cancels the asyncio task but cannot kill ``to_thread``;
Activation is gated by ``IndexingRunRegistry`` + ``[Generation Guard]`` logs.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.rag.handlers import (
    RAG_INDEX_TIMEOUT_WARNING,
    _compensate_revoked_index_run,
    _index_with_heartbeat_and_timeout,
    _revoke_and_schedule_orphan_cleanup,
)
from backend.rag.indexing_run_registry import get_indexing_run_registry
from backend.rag.models import PaperChunk
from backend.rag.vector_store import GENERATION_GUARD_LOG_PREFIX, VectorStore
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service

from tests.rag.test_vector_store import FakeCollection, FakeEmbeddingClient, _matches_where

PAPER_ID = "paper-race-x"
RUN_A = "run_a"
RUN_B = "run_b"
TIMEOUT_SECONDS = 1.0
GATE_HOLD_SECONDS = 2.0


class LatencyGate:
    """Hold sync upserts for selected index_run_id values until released."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._holds: dict[str, threading.Event] = {}
        self.entered: dict[str, threading.Event] = {}

    def arm(self, run_id: str) -> None:
        with self._lock:
            self._holds[run_id] = threading.Event()
            self.entered[run_id] = threading.Event()

    def release(self, run_id: str) -> None:
        with self._lock:
            event = self._holds.get(run_id)
        if event is not None:
            event.set()

    def wait_if_armed(self, run_id: str | None) -> None:
        if not run_id:
            return
        with self._lock:
            hold = self._holds.get(run_id)
            entered = self.entered.get(run_id)
        if entered is not None:
            entered.set()
        if hold is not None:
            hold.wait(timeout=30.0)


class GatedFakeCollection(FakeCollection):
    """FakeCollection whose upsert blocks on LatencyGate by metadata.index_run_id."""

    def __init__(self, gate: LatencyGate) -> None:
        super().__init__()
        self._gate = gate

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[Any],
    ) -> None:
        run_id = None
        if metadatas:
            run_id = metadatas[0].get("index_run_id")
        self._gate.wait_if_armed(run_id if isinstance(run_id, str) else None)
        super().upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def _chunk(paper_id: str, text: str, *, index: int = 0) -> PaperChunk:
    return PaperChunk(
        chunk_id=f"{paper_id}:chunk:{index}",
        paper_id=paper_id,
        text=text,
        section="body",
        chunk_index=index,
        source="pymupdf",
        char_start=0,
        char_end=len(text),
    )


def _records_for_run(collection: FakeCollection, run_id: str) -> list[str]:
    return [
        record_id
        for record_id, record in collection.records.items()
        if _matches_where(record["metadata"], {"index_run_id": run_id})
    ]


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    get_indexing_run_registry().reset()
    yield
    get_indexing_run_registry().reset()


@pytest.mark.asyncio
@pytest.mark.p13_release_gate
async def test_orphan_thread_cannot_override_new_generation(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """并发/时域：A 超时 → B 成功 → A 僵尸写完后数据世代仍属 B（Run ID 双检）."""
    caplog.set_level(logging.WARNING)
    gate = LatencyGate()
    gate.arm(RUN_A)

    paper_state = {
        "status": PaperStatus.INDEXING,
        "active_run_id": None,
        "warnings": [],
        "set_active_calls": [],
    }

    paper_service = MagicMock()
    paper_service.get_active_run_id = AsyncMock(side_effect=lambda _pid: paper_state["active_run_id"])

    def _set_active(paper_id: str, run_id: str) -> None:
        paper_state["set_active_calls"].append((paper_id, run_id))
        paper_state["active_run_id"] = run_id or None
        if run_id == RUN_B:
            paper_state["status"] = PaperStatus.READY

    paper_service.set_active_run_id = AsyncMock(side_effect=_set_active)

    chunk_collection = GatedFakeCollection(gate)
    entity_collection = FakeCollection()
    relation_collection = FakeCollection()
    store = VectorStore(
        paper_service=paper_service,
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=chunk_collection,
        entity_collection=entity_collection,
        relation_collection=relation_collection,
    )

    run_ids = iter([RUN_A, RUN_B, "run_probe"])
    cleanup_tasks: list[asyncio.Task[None]] = []

    def _schedule_fast_cleanup(paper_id: str, run_id: str) -> None:
        # First pass may race before zombie upsert; retries after GATE_HOLD.
        task = asyncio.create_task(
            _compensate_revoked_index_run(
                paper_id,
                run_id,
                delays_seconds=(0.0, 1.2, 1.5),
            ),
            name=f"test-orphan-cleanup:{paper_id}:{run_id}",
        )
        cleanup_tasks.append(task)

    async def _index_fn(paper_id: str, **_kwargs: object) -> bool:
        await store.replace_paper_index(
            paper_id,
            chunks=[_chunk(paper_id, "run-a body text for embeddings")],
            entities=[],
            relations=[],
        )
        return True

    monkeypatch.setattr(
        "backend.rag.handlers._schedule_orphan_run_cleanup",
        _schedule_fast_cleanup,
    )
    monkeypatch.setattr(
        "backend.rag.handlers.get_paper_service",
        lambda: paper_service,
    )
    monkeypatch.setattr(
        "backend.rag.handlers.get_vector_store",
        lambda: store,
    )

    with (
        patch("backend.rag.vector_store_replace._generate_run_id", side_effect=lambda: next(run_ids)),
        patch.object(
            get_paper_service(),
            "touch_indexing_heartbeat",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        # --- Run A: expect micro-timeout at TIMEOUT_SECONDS ---
        with pytest.raises(TimeoutError):
            await _index_with_heartbeat_and_timeout(
                PAPER_ID,
                full_text="unused",
                graph=MagicMock(),
                page_break_offsets=None,
                timeout_seconds=TIMEOUT_SECONDS,
                heartbeat_interval_seconds=60.0,
                index_fn=_index_fn,
            )

        # Timeout handling: promote + revoke semantics (handler would persist this).
        paper_state["status"] = PaperStatus.READY_WITH_WARNINGS
        paper_state["warnings"] = [RAG_INDEX_TIMEOUT_WARNING]
        assert paper_state["active_run_id"] is None
        assert RUN_A not in {rid for _pid, rid in paper_state["set_active_calls"] if rid}
        assert get_indexing_run_registry().may_activate(PAPER_ID, RUN_A) is False
        assert GENERATION_GUARD_LOG_PREFIX in caplog.text
        assert f"{GENERATION_GUARD_LOG_PREFIX} {RUN_A} is obsolete" in caplog.text

        # Wait until the zombie upsert thread is inside the gate (still held).
        assert gate.entered[RUN_A].wait(timeout=2.0)

        # --- Run B: fast successor while Run A thread is still blocked ---
        await store.replace_paper_index(
            PAPER_ID,
            chunks=[_chunk(PAPER_ID, "run-b successor body text for embeddings")],
            entities=[],
            relations=[],
        )
        assert paper_state["status"] == PaperStatus.READY
        assert paper_state["active_run_id"] == RUN_B
        assert _records_for_run(chunk_collection, RUN_B)

        # --- Release zombie Run A (≈2s): late upsert, then refuse to stay active ---
        gate.release(RUN_A)
        # Let the executor thread finish the deferred upsert.
        await asyncio.sleep(0.25)
        for task in cleanup_tasks:
            await asyncio.wait_for(task, timeout=5.0)

        # Invariant 1 — status must not regress to WARNINGS under Run A complete logic.
        assert paper_state["status"] == PaperStatus.READY
        assert paper_state["active_run_id"] == RUN_B
        assert RUN_A not in {rid for _pid, rid in paper_state["set_active_calls"] if rid}

        # Invariant 3 — no Run A residue after compensating cleanup.
        assert _records_for_run(chunk_collection, RUN_A) == []
        assert _records_for_run(chunk_collection, RUN_B)

        # Invariant 2 — Generation Guard must refuse a superseded activate while B is live.
        registry = get_indexing_run_registry()
        real_begin = registry.begin

        def _begin_then_revoke(paper_id: str, run_id: str) -> None:
            real_begin(paper_id, run_id)
            registry.revoke(paper_id, run_id)

        caplog.clear()
        with patch.object(registry, "begin", side_effect=_begin_then_revoke):
            await store.replace_paper_index(
                PAPER_ID,
                chunks=[_chunk(PAPER_ID, "probe obsolete activate path", index=9)],
                entities=[],
                relations=[],
            )
        assert (
            f"{GENERATION_GUARD_LOG_PREFIX} run_probe is obsolete (current active is {RUN_B}). "
            "Aborting database update."
        ) in caplog.text
        assert paper_state["active_run_id"] == RUN_B
        assert paper_state["status"] == PaperStatus.READY


@pytest.mark.asyncio
@pytest.mark.p13_release_gate
async def test_cleanup_task_removes_delayed_orphan_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自愈/补偿：A 超时后僵尸 upsert 仍会落 Chroma，补偿 delete_run 必须扫净."""
    gate = LatencyGate()
    gate.arm(RUN_A)

    paper_state: dict[str, object] = {"active_run_id": None}
    paper_service = MagicMock()
    paper_service.get_active_run_id = AsyncMock(side_effect=lambda _pid: paper_state["active_run_id"])
    paper_service.set_active_run_id = AsyncMock(
        side_effect=lambda _pid, rid: paper_state.__setitem__(
            "active_run_id",
            rid or None,
        ),
    )

    chunk_collection = GatedFakeCollection(gate)
    store = VectorStore(
        paper_service=paper_service,
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=chunk_collection,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )
    cleanup_tasks: list[asyncio.Task[None]] = []

    def _schedule_cleanup(paper_id: str, run_id: str) -> None:
        # First pass may race before the zombie upsert; retry after release.
        cleanup_tasks.append(
            asyncio.create_task(
                _compensate_revoked_index_run(
                    paper_id,
                    run_id,
                    delays_seconds=(0.05, 0.45),
                ),
                name=f"test-cleanup:{paper_id}:{run_id}",
            )
        )

    async def _index_fn(paper_id: str, **_kwargs: object) -> bool:
        await store.replace_paper_index(
            paper_id,
            chunks=[_chunk(paper_id, "orphan cleanup body for embeddings")],
            entities=[],
            relations=[],
        )
        return True

    monkeypatch.setattr("backend.rag.handlers._schedule_orphan_run_cleanup", _schedule_cleanup)
    monkeypatch.setattr("backend.rag.handlers.get_paper_service", lambda: paper_service)
    monkeypatch.setattr("backend.rag.handlers.get_vector_store", lambda: store)

    with (
        patch("backend.rag.vector_store_replace._generate_run_id", return_value=RUN_A),
        patch.object(
            get_paper_service(),
            "touch_indexing_heartbeat",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        with pytest.raises(TimeoutError):
            await _index_with_heartbeat_and_timeout(
                PAPER_ID,
                full_text="unused",
                graph=MagicMock(),
                page_break_offsets=None,
                timeout_seconds=TIMEOUT_SECONDS,
                heartbeat_interval_seconds=60.0,
                index_fn=_index_fn,
            )

        assert gate.entered[RUN_A].wait(timeout=2.0)
        assert cleanup_tasks
        # Release the zombie write after timeout revoke/schedule, before the late retry.
        await asyncio.sleep(0.15)
        gate.release(RUN_A)
        await asyncio.sleep(0.2)
        # Zombie thread may have written; compensate retries must erase it.
        for task in cleanup_tasks:
            await asyncio.wait_for(task, timeout=5.0)

        assert paper_state["active_run_id"] is None
        assert _records_for_run(chunk_collection, RUN_A) == []
        # Compensate ends with registry.clear — revoke sticky only until delete_run finishes.


@pytest.mark.asyncio
async def test_generation_guard_log_names_current_active_run(caplog: pytest.LogCaptureFixture) -> None:
    """Refuse-activate path must name the live successor in the Generation Guard line."""
    caplog.set_level(logging.WARNING)
    paper_service = MagicMock()
    paper_service.get_active_run_id = AsyncMock(return_value=RUN_B)
    paper_service.set_active_run_id = AsyncMock()
    store = VectorStore(
        paper_service=paper_service,
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=FakeCollection(),
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )
    registry = get_indexing_run_registry()
    real_begin = registry.begin

    def _begin_then_revoke(paper_id: str, run_id: str) -> None:
        real_begin(paper_id, run_id)
        registry.revoke(paper_id, run_id)

    with (
        patch("backend.rag.vector_store_replace._generate_run_id", return_value=RUN_A),
        patch.object(registry, "begin", side_effect=_begin_then_revoke),
    ):
        await store.replace_paper_index(
            PAPER_ID,
            chunks=[_chunk(PAPER_ID, "stale run body")],
            entities=[],
            relations=[],
        )

    paper_service.set_active_run_id.assert_not_called()
    assert (
        f"{GENERATION_GUARD_LOG_PREFIX} {RUN_A} is obsolete (current active is {RUN_B}). Aborting database update."
    ) in caplog.text


@pytest.mark.asyncio
async def test_revoke_helper_still_schedules_cleanup_after_timeout_path() -> None:
    """Smoke: TimeoutError path helper continues to revoke + schedule compensate."""
    registry = get_indexing_run_registry()
    registry.begin(PAPER_ID, RUN_A)
    scheduled: list[tuple[str, str]] = []

    with patch(
        "backend.rag.handlers._schedule_orphan_run_cleanup",
        side_effect=lambda pid, rid: scheduled.append((pid, rid)),
    ):
        assert _revoke_and_schedule_orphan_cleanup(PAPER_ID) == RUN_A

    assert scheduled == [(PAPER_ID, RUN_A)]
    assert registry.may_activate(PAPER_ID, RUN_A) is False
