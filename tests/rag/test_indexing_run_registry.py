"""Unit tests for indexing run generation registry + activation gate."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.rag.indexing_run_registry import IndexingRunRegistry, get_indexing_run_registry
from backend.rag.models import PaperChunk
from backend.rag.vector_store import VectorStore


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    get_indexing_run_registry().reset()
    yield
    get_indexing_run_registry().reset()


def test_registry_revoke_blocks_activation() -> None:
    registry = IndexingRunRegistry()
    registry.begin("p1", "run_a")
    assert registry.may_activate("p1", "run_a") is True
    assert registry.revoke("p1") == "run_a"
    assert registry.may_activate("p1", "run_a") is False
    assert registry.peek_inflight("p1") is None


def test_registry_begin_clears_prior_revoke_for_same_run() -> None:
    registry = IndexingRunRegistry()
    registry.begin("p1", "run_a")
    registry.revoke("p1", "run_a")
    registry.begin("p1", "run_a")
    assert registry.may_activate("p1", "run_a") is True


def test_registry_revoke_returns_already_revoked_for_cleanup_schedule() -> None:
    """After cancel path revokes, timeout-path revoke(paper_id) must still yield the id."""
    registry = IndexingRunRegistry()
    registry.begin("p1", "run_a")
    assert registry.revoke("p1") == "run_a"
    assert registry.peek_inflight("p1") is None
    assert registry.revoke("p1") == "run_a"
    assert registry.may_activate("p1", "run_a") is False


def test_may_activate_requires_inflight_generation_match() -> None:
    """Dual gate: a superseded run cannot activate even if not (yet) in revoke set."""
    registry = IndexingRunRegistry()
    registry.begin("p1", "run_a")
    registry.begin("p1", "run_b")
    assert registry.may_activate("p1", "run_a") is False
    assert registry.may_activate("p1", "run_b") is True


def test_sticky_revoke_returns_most_recent_for_paper() -> None:
    """When multiple revoked ids exist, revoke(paper_id) returns the latest one."""
    registry = IndexingRunRegistry()
    registry.begin("p1", "run_a")
    assert registry.revoke("p1", "run_a") == "run_a"
    registry.begin("p1", "run_b")
    assert registry.revoke("p1", "run_b") == "run_b"
    assert registry.revoke("p1") == "run_b"


@pytest.mark.asyncio
async def test_replace_paper_index_skips_activate_when_revoked() -> None:
    """After begin+revoke, upsert may finish but must not call set_active_run_id."""
    paper_service = MagicMock()
    paper_service.get_active_run_id.return_value = None
    set_active = MagicMock()
    paper_service.set_active_run_id = set_active

    chunk_collection = MagicMock()
    entity_collection = MagicMock()
    relation_collection = MagicMock()
    store = VectorStore(
        paper_service=paper_service,
        embedding_client=MagicMock(embed_texts=AsyncMock(return_value=[[0.1, 0.2]])),
        chunk_collection=chunk_collection,
        entity_collection=entity_collection,
        relation_collection=relation_collection,
    )

    registry = get_indexing_run_registry()
    real_begin = registry.begin
    captured_run: dict[str, str] = {}

    def begin_then_revoke(paper_id: str, run_id: str) -> None:
        captured_run["run_id"] = run_id
        real_begin(paper_id, run_id)
        registry.revoke(paper_id, run_id)

    with patch.object(registry, "begin", side_effect=begin_then_revoke):
        await store.replace_paper_index(
            "paper-revoked",
            chunks=[
                PaperChunk(
                    chunk_id="paper-revoked:chunk:0",
                    paper_id="paper-revoked",
                    text="hello world for embedding",
                    section="body",
                    chunk_index=0,
                    source="pymupdf",
                    char_start=0,
                    char_end=24,
                ),
            ],
            entities=[],
            relations=[],
        )

    set_active.assert_not_called()
    # Compensating cleanup on revoked path uses collection.delete via to_thread.
    assert chunk_collection.delete.called
    # Revoke stays sticky until orphan compensate / successful activate clear().
    assert captured_run["run_id"]
    assert registry.may_activate("paper-revoked", captured_run["run_id"]) is False


@pytest.mark.asyncio
async def test_compensate_revoked_run_clears_active_pointer() -> None:
    from backend.rag.handlers import _compensate_revoked_index_run

    paper_service = MagicMock()
    paper_service.get_active_run_id.return_value = "run_stale"
    paper_service.set_active_run_id = MagicMock()
    store = MagicMock()
    store.delete_run = AsyncMock()

    with (
        patch("backend.rag.handlers.get_paper_service", return_value=paper_service),
        patch("backend.rag.handlers.VectorStore", return_value=store),
    ):
        await _compensate_revoked_index_run(
            "paper-x",
            "run_stale",
            delays_seconds=(0.0,),
        )

    paper_service.set_active_run_id.assert_called_with("paper-x", None)
    store.delete_run.assert_awaited_once_with("paper-x", "run_stale")


@pytest.mark.asyncio
async def test_timeout_path_revokes_and_schedules_cleanup() -> None:
    from backend.rag import handlers as handlers_module

    registry = get_indexing_run_registry()
    registry.begin("timeout-paper", "run_t1")

    scheduled: list[tuple[str, str]] = []

    def capture_schedule(paper_id: str, run_id: str) -> None:
        scheduled.append((paper_id, run_id))

    with patch.object(handlers_module, "_schedule_orphan_run_cleanup", side_effect=capture_schedule):
        revoked = handlers_module._revoke_and_schedule_orphan_cleanup("timeout-paper")

    assert revoked == "run_t1"
    assert scheduled == [("timeout-paper", "run_t1")]
    assert registry.may_activate("timeout-paper", "run_t1") is False


@pytest.mark.asyncio
async def test_wait_for_timeout_revokes_before_reraising() -> None:
    from backend.rag.handlers import _index_with_heartbeat_and_timeout

    registry = get_indexing_run_registry()

    async def slow_index(paper_id: str, **_kwargs: object) -> bool:
        registry.begin(paper_id, "run_slow")
        await asyncio.sleep(60)
        return True

    with (
        patch(
            "backend.repositories.pipeline_repository.get_pipeline_repository",
            return_value=MagicMock(touch_indexing_heartbeat=AsyncMock()),
        ),
        patch("backend.rag.handlers._schedule_orphan_run_cleanup"),
    ):
        with pytest.raises(TimeoutError):
            await _index_with_heartbeat_and_timeout(
                "paper-slow",
                full_text="x",
                graph=MagicMock(),
                page_break_offsets=None,
                timeout_seconds=0.01,
                heartbeat_interval_seconds=60.0,
                index_fn=slow_index,
            )

    assert registry.may_activate("paper-slow", "run_slow") is False
