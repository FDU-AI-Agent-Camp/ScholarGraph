"""P13 indexing watchdog — micro wait_for + macro sweep / heartbeat boundaries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.db.base import get_async_session_factory
from backend.db.models import PipelineRunRow
from backend.events.bus import get_event_bus
from backend.events.types import PipelineFinalized, RagIndexed
from backend.graph.state import STAGE_PERCENT
from backend.rag.handlers import RAG_INDEX_TIMEOUT_WARNING, on_pipeline_finalized_for_rag
from backend.rag.indexing_watchdog import (
    RAG_INDEXING_STUCK_WARNING,
    WATCHDOG_THREAD_NAME,
    reset_watchdog_sync_engine,
    scan_and_promote_stuck_indexing,
    start_indexing_watchdog,
    stop_indexing_watchdog,
    watchdog_thread_is_alive,
)
from backend.repositories.async_bridge import run_async
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage

from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset
from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_test_paper,
    reset_persistence_singletons,
)


@pytest.fixture
def watchdog_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "watchdog.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("RAG_INDEXING_WATCHDOG_ENABLED", "true")
    get_settings.cache_clear()
    reset_persistence_singletons()
    reset_watchdog_sync_engine()
    stop_indexing_watchdog()
    run_async(init_isolated_database(db_path))
    yield
    stop_indexing_watchdog()
    reset_watchdog_sync_engine()
    reset_persistence_singletons()
    get_settings.cache_clear()


async def _put_paper_indexing(
    paper_id: str,
    *,
    started_at: datetime,
    heartbeat_at: datetime | None = None,
) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.INDEXING,
        percent=STAGE_PERCENT[PipelineStage.INDEXING],
        stage=PipelineStage.INDEXING,
        message="indexing",
        updated_at=datetime.now(UTC),
        extract_warnings=[],
    )
    await get_pipeline_repository().save_status(paper_id, snapshot)
    pulse = heartbeat_at if heartbeat_at is not None else started_at
    async with get_async_session_factory()() as session:
        run = await session.get(PipelineRunRow, paper_id)
        assert run is not None
        run.indexing_started_at = started_at
        run.indexing_heartbeat = pulse
        run.updated_at = pulse
        await session.commit()


# ---------------------------------------------------------------------------
# Macro: zombie sweep / margin / heartbeat safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_macro_zombie_scan_promotes_and_emits_rag_indexed_false(
    watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """论文 A：indexing_started_at = now-1h → 扫尾强制 READY_WITH_WARNINGS + RagIndexed(False)."""
    started = datetime.now(UTC) - timedelta(hours=1)
    await _put_paper_indexing("paper-a", started_at=started, heartbeat_at=started)

    seen: list[RagIndexed] = []
    bus = get_event_bus()
    original_publish_sync = bus.publish_sync

    def _capture_publish_sync(event: object) -> None:
        if isinstance(event, RagIndexed):
            seen.append(event)
        original_publish_sync(event)

    monkeypatch.setattr(bus, "publish_sync", _capture_publish_sync)

    promoted = await scan_and_promote_stuck_indexing(
        stuck_after_seconds=60.0,
        heartbeat_stale_seconds=90.0,
    )

    assert promoted == ["paper-a"]
    latest = await get_pipeline_repository().get_latest("paper-a")
    assert latest is not None
    assert latest.status == PaperStatus.READY_WITH_WARNINGS
    assert RAG_INDEXING_STUCK_WARNING in latest.extract_warnings
    assert len(seen) == 1
    assert seen[0].paper_id == "paper-a"
    assert seen[0].success is False
    assert seen[0].terminal_status == PaperStatus.READY_WITH_WARNINGS


@pytest.mark.asyncio
async def test_macro_margin_keeps_indexing_at_58s_of_60s_threshold(watchdog_db) -> None:
    """论文 B：started = now-58s，阈值 60s → 边界内保留 indexing（防 1s 越界误杀）."""
    now = datetime.now(UTC)
    started = now - timedelta(seconds=58)
    await _put_paper_indexing("paper-b", started_at=started, heartbeat_at=started)

    promoted = await scan_and_promote_stuck_indexing(
        now=now,
        stuck_after_seconds=60.0,
        heartbeat_stale_seconds=90.0,
    )
    assert promoted == []
    latest = await get_pipeline_repository().get_latest("paper-b")
    assert latest is not None
    assert latest.status == PaperStatus.INDEXING


@pytest.mark.asyncio
async def test_macro_active_heartbeat_prevents_promote_of_long_index(watchdog_db) -> None:
    """论文 C：started 超阈值，但 heartbeat 仅 5s 前 → 视为活任务，不得误杀。"""
    now = datetime.now(UTC)
    started = now - timedelta(minutes=2)
    heartbeat = now - timedelta(seconds=5)
    await _put_paper_indexing("paper-c", started_at=started, heartbeat_at=heartbeat)

    promoted = await scan_and_promote_stuck_indexing(
        now=now,
        stuck_after_seconds=60.0,
        heartbeat_stale_seconds=90.0,
    )
    assert promoted == []
    latest = await get_pipeline_repository().get_latest("paper-c")
    assert latest is not None
    assert latest.status == PaperStatus.INDEXING


@pytest.mark.asyncio
@pytest.mark.p13_release_gate
async def test_cold_boot_reconciliation_clears_zombie_states(
    watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """临界自愈：startup lifespan 瞬间清洗历史 INDEXING 僵尸，无脏状态残留。"""
    stale = datetime.now(UTC) - timedelta(hours=2)
    zombie_ids = ("zombie-a", "zombie-b", "zombie-c")
    for pid in zombie_ids:
        await _put_paper_indexing(pid, started_at=stale, heartbeat_at=stale)

    # Keep lifespan side-effects light for the unit suite.
    async def _noop_probe(_settings) -> None:
        return None

    monkeypatch.setattr(
        "backend.startup.profile_validation.probe_reranker_connectivity",
        _noop_probe,
    )
    monkeypatch.setattr(
        "backend.rag.hybrid_retriever.create_hybrid_retriever",
        lambda: object(),
    )
    monkeypatch.setattr("backend.rag.hybrid_retriever.bind_hybrid_retriever", lambda _r: None)
    monkeypatch.setattr("backend.rag.hybrid_retriever.reset_hybrid_retriever", lambda: None)

    from backend.main import create_app, lifespan

    app = create_app()
    # Entering the context runs startup (incl. reconcile) before the body.
    async with lifespan(app):
        for pid in zombie_ids:
            latest = await get_pipeline_repository().get_latest(pid)
            assert latest is not None
            assert latest.status == PaperStatus.READY_WITH_WARNINGS, pid
            assert RAG_INDEXING_STUCK_WARNING in latest.extract_warnings


# ---------------------------------------------------------------------------
# Micro: hang cut by wait_for
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_micro_handler_hang_is_cut_by_wait_for_and_promotes_terminal(
    watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """微观超时拦截：index hang 时 wait_for 掐断，内部吞掉 TimeoutError，终态带超时归因。"""
    import asyncio

    await _put_paper_indexing("timeout-001", started_at=datetime.now(UTC))
    monkeypatch.setenv("RAG_SINGLE_INDEX_TIMEOUT_SECONDS", "0.1")
    get_settings.cache_clear()
    assert get_settings().rag_single_index_timeout_seconds == 0.1

    async def _hang_forever(*_args, **_kwargs):
        await asyncio.sleep(9999)
        return True

    monkeypatch.setattr(
        "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
        _hang_forever,
    )

    graph = build_stem_graph_with_method_dataset(
        "timeout-001",
        method_label="PCA",
        dataset_label="MNIST",
    )
    event = PipelineFinalized(
        paper_id="timeout-001",
        full_text="x" * 200,
        graph=graph,
        terminal_status=PaperStatus.READY,
    )

    with caplog.at_level(logging.ERROR, logger="backend.rag.handlers"):
        await on_pipeline_finalized_for_rag(event)

    assert any(record.message == "pipeline_finalized_rag_index_timeout" for record in caplog.records)

    latest = await get_pipeline_repository().get_latest("timeout-001")
    assert latest is not None
    assert latest.status == PaperStatus.READY_WITH_WARNINGS
    assert latest.stage == PipelineStage.READY
    assert RAG_INDEX_TIMEOUT_WARNING in latest.extract_warnings
    assert "超时" in (latest.message or "")
    assert latest.percent == STAGE_PERCENT[PipelineStage.READY]


@pytest.mark.asyncio
async def test_handler_promote_idempotent_after_watchdog_already_terminal(
    watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Watchdog sync-promote first; late handler promote must not raise / pollute warnings."""
    from unittest.mock import AsyncMock

    from backend.events.handler_errors import EVENT_HANDLER_FAILED_CODE
    from backend.rag.handlers import _promote_terminal_status
    from backend.rag.indexing_watchdog import promote_stuck_indexing_paper
    from backend.services.paper_service import get_paper_service

    paper_id = "idempotent-race-001"
    started = datetime.now(UTC) - timedelta(hours=1)
    await _put_paper_indexing(paper_id, started_at=started, heartbeat_at=started)
    assert await promote_stuck_indexing_paper(paper_id) is True

    latest = await get_pipeline_repository().get_latest(paper_id)
    assert latest is not None
    assert latest.status == PaperStatus.READY_WITH_WARNINGS
    warnings_before = list(latest.extract_warnings)

    graph = build_stem_graph_with_method_dataset(
        paper_id,
        method_label="PCA",
        dataset_label="MNIST",
    )
    event = PipelineFinalized(
        paper_id=paper_id,
        full_text="x" * 200,
        graph=graph,
        terminal_status=PaperStatus.READY,
    )

    # Late promote path after macro heal (also exercises full handler optional).
    await _promote_terminal_status(event, success=True)

    monkeypatch.setattr(
        "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
        AsyncMock(return_value=True),
    )
    await on_pipeline_finalized_for_rag(event)

    after = await get_paper_service().get_pipeline_snapshot(paper_id)
    assert after is not None
    assert after.status == PaperStatus.READY_WITH_WARNINGS
    assert after.extract_warnings == warnings_before
    assert not any(EVENT_HANDLER_FAILED_CODE in item for item in after.extract_warnings)
    assert not any("refuse promote" in item for item in after.extract_warnings)


@pytest.mark.asyncio
async def test_e2e_watchdog_promote_then_patrol_api_degrades_index_not_ready(
    watchdog_db,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P13→P9 E2E：看门狗强制终态后 Patrol HTTP 200 且 is_degraded + INDEX_NOT_READY。"""
    from backend.api.routes import patrol as patrol_routes
    from backend.graph.store import GraphStore
    from backend.main import app
    from backend.patrol.result_cache import InMemoryPatrolResultCache
    from backend.schemas.patrol import PatrolMode
    from backend.services import patrol_service as ps_module
    from backend.services.patrol_service import PatrolService
    from httpx import ASGITransport, AsyncClient

    from tests.patrol.conftest import reset_patrol_runtime_caches

    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()

    store = GraphStore(base_dir=graph_dir)
    stale = datetime.now(UTC) - timedelta(hours=1)
    for pid in ("stem-w1", "stem-w2"):
        await _put_paper_indexing(pid, started_at=stale, heartbeat_at=stale)
        store.save(
            build_stem_graph_with_method_dataset(pid, method_label="PCA", dataset_label="MNIST"),
        )

    # Step 1→2: stuck indexing → watchdog promote
    promoted = await scan_and_promote_stuck_indexing(
        stuck_after_seconds=60.0,
        heartbeat_stale_seconds=90.0,
    )
    assert set(promoted) == {"stem-w1", "stem-w2"}
    for pid in promoted:
        latest = await get_pipeline_repository().get_latest(pid)
        assert latest is not None
        assert latest.status == PaperStatus.READY_WITH_WARNINGS

    class _MissingIndexStore:
        async def exists(self, paper_id: str) -> bool:
            return False

        async def query_chunks(self, *_a, **_k):
            return []

    service = PatrolService(
        store=store,
        vector_store=_MissingIndexStore(),  # type: ignore[arg-type]
        result_cache=InMemoryPatrolResultCache(),
        cache_enabled=False,
        paper_fingerprint_fn=lambda ids: ";".join(f"{pid}@1.0.0/-" for pid in ids),
    )
    monkeypatch.setattr(ps_module, "get_patrol_service", lambda: service)
    app.dependency_overrides[patrol_routes.get_patrol_service_dep] = lambda: service
    reset_patrol_runtime_caches()

    # Step 3: Patrol method_overlap over HTTP
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/patrol",
            json={"paper_ids": ["stem-w1", "stem-w2"], "mode": PatrolMode.METHOD_OVERLAP.value},
        )

    assert response.status_code == 200
    body = response.json()
    insight = body["data"]["insights"][0]
    assert insight["is_degraded"] is True
    assert insight["degradation_profile"]["reason_code"] == "INDEX_NOT_READY"

    app.dependency_overrides.clear()


def test_watchdog_runs_on_dedicated_daemon_thread(
    watchdog_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Macro watchdog must not be an asyncio.Task on the FastAPI loop."""
    import threading
    import time
    from unittest.mock import patch

    monkeypatch.setenv("RAG_INDEXING_WATCHDOG_INTERVAL_SECONDS", "0.05")
    get_settings.cache_clear()
    scan_calls = {"n": 0}

    def _counting_scan(**_kwargs):
        scan_calls["n"] += 1
        return []

    stop_indexing_watchdog()
    with patch(
        "backend.rag.indexing_watchdog.scan_and_promote_stuck_indexing_sync",
        side_effect=_counting_scan,
    ):
        start_indexing_watchdog()
        assert watchdog_thread_is_alive()
        names = {t.name for t in threading.enumerate()}
        assert WATCHDOG_THREAD_NAME in names
        deadline = time.monotonic() + 2.0
        while scan_calls["n"] < 1 and time.monotonic() < deadline:
            time.sleep(0.05)
        stop_indexing_watchdog()
    assert scan_calls["n"] >= 1
    assert not watchdog_thread_is_alive()


def test_asyncio_block_detector_auto_enables_in_test_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from backend.startup.asyncio_debug import configure_asyncio_block_detector

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ASYNCIO_SLOW_CALLBACK_MS", "-1")
    get_settings.cache_clear()
    loop = asyncio.new_event_loop()
    try:
        assert configure_asyncio_block_detector(loop) is True
        assert loop.get_debug() is True
        assert loop.slow_callback_duration == pytest.approx(0.1)
    finally:
        loop.close()
        get_settings.cache_clear()
