# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Chaos & resilience matrix — event-loop starvation, partition, cold-boot heal.

Ship today (in-process, no Testcontainers):
- Indexing / processing Watchdog ticks + commits while main loop ``time.sleep`` starves
- Cold-boot lifespan reconciles PROCESSING → PROCESS_ORPHANED and INDEXING → stuck warning
- Vector-store partition maps to VECTOR_STORE_UNAVAILABLE (HTTP ≠ 500) and recovers after probe

Deferred (``architecture_evolution``): kill real Chroma/Redis containers + Redlock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import get_settings
from backend.db.base import get_async_session_factory
from backend.db.models import PaperRow, PipelineRunRow
from backend.graph.state import STAGE_PERCENT
from backend.pipeline.processing_watchdog import (
    PROCESS_ORPHANED_CODE,
    reset_processing_watchdog_sync_engine,
    stop_processing_watchdog,
)
from backend.rag.indexing_watchdog import (
    RAG_INDEXING_STUCK_WARNING,
    reset_watchdog_sync_engine,
    stop_indexing_watchdog,
)
from backend.repositories.async_bridge import run_async
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_test_paper,
    reset_persistence_singletons,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Catalog of shipping chaos proofs (prevents silent rename / delete of defenses).
CHAOS_RESILIENCE_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "主循环饥饿/INDEXING Watchdog",
        "test_watchdog_works_during_event_loop_starvation",
        "tests/rag/test_watchdog_main_loop_starvation.py",
    ),
    (
        "主循环饥饿/PROCESSING Watchdog",
        "test_processing_watchdog_survives_loop_starvation",
        "tests/pipeline/test_processing_watchdog_loop_starvation.py",
    ),
    (
        "冷启动/INDEXING 僵尸",
        "test_cold_boot_reconciliation_clears_zombie_states",
        "tests/rag/test_indexing_watchdog.py",
    ),
    (
        "冷启动/PROCESSING 僵尸",
        "test_boot_reconciliation_processing",
        "tests/regression/test_self_heal_control_gates.py",
    ),
    (
        "分区降级/VECTOR_STORE_UNAVAILABLE",
        "test_vector_store_recovers_full_retrieval_after_transient_outage",
        "tests/integration/test_vector_store_resilience_boundaries.py",
    ),
    (
        "分区降级/SSE 自愈",
        "test_sse_self_heals_after_transient_vector_store_outage",
        "tests/integration/test_vector_store_resilience_boundaries.py",
    ),
    (
        "DELETE 硬失败/幽灵向量阻断",
        "test_delete_vector_timeout_hard_fails_without_sql_wipe",
        "tests/services/test_paper_delete_service.py",
    ),
)


@pytest.fixture
def chaos_boot_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "chaos_boot.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    monkeypatch.setenv("PROCESS_WATCHDOG_ENABLED", "true")
    monkeypatch.setenv("PROCESS_ORPHAN_GRACE_SECONDS", "10")
    monkeypatch.setenv("RAG_INDEXING_WATCHDOG_ENABLED", "true")
    get_settings.cache_clear()
    reset_persistence_singletons()
    reset_processing_watchdog_sync_engine()
    reset_watchdog_sync_engine()
    stop_processing_watchdog()
    stop_indexing_watchdog()
    run_async(init_isolated_database(db_path))
    yield
    stop_processing_watchdog()
    stop_indexing_watchdog()
    reset_processing_watchdog_sync_engine()
    reset_watchdog_sync_engine()
    reset_persistence_singletons()
    get_settings.cache_clear()


async def _put_stale_processing(paper_id: str, *, updated_at: datetime) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        stage=PipelineStage.EXTRACTING,
        message="processing",
        updated_at=datetime.now(UTC),
    )
    await get_pipeline_repository().save_status(paper_id, snapshot)
    async with get_async_session_factory()() as session:
        run = await session.get(PipelineRunRow, paper_id)
        paper = await session.get(PaperRow, paper_id)
        assert run is not None and paper is not None
        run.updated_at = updated_at
        paper.updated_at = updated_at
        paper.status = PaperStatus.PROCESSING.value
        await session.commit()


async def _put_stale_indexing(paper_id: str, *, started_at: datetime) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    snapshot = PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.INDEXING,
        percent=STAGE_PERCENT[PipelineStage.INDEXING],
        stage=PipelineStage.INDEXING,
        message="indexing",
        updated_at=started_at,
    )
    await get_pipeline_repository().save_status(paper_id, snapshot)
    async with get_async_session_factory()() as session:
        run = await session.get(PipelineRunRow, paper_id)
        paper = await session.get(PaperRow, paper_id)
        assert run is not None and paper is not None
        run.indexing_started_at = started_at
        run.indexing_heartbeat = started_at
        run.updated_at = started_at
        paper.updated_at = started_at
        paper.status = PaperStatus.INDEXING.value
        await session.commit()


def test_chaos_resilience_catalog_is_complete() -> None:
    """Wiring gate only: ensures named production chaos proofs still exist on disk.

    Behavioral proofs live in the referenced modules (and below). This test does
    not claim to exercise runtime heal paths — it prevents silent rename/delete.
    """
    missing: list[str] = []
    for _category, test_name, rel_path in CHAOS_RESILIENCE_CASES:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            missing.append(f"{test_name} (missing file {rel_path})")
            continue
        text = path.read_text(encoding="utf-8")
        if f"def {test_name}(" not in text:
            missing.append(f"{test_name} (not defined in {rel_path})")
    assert missing == [], "Chaos resilience catalog regressions:\n" + "\n".join(missing)


@pytest.mark.asyncio
async def test_cold_boot_reconciles_processing_and_indexing_zombies(
    chaos_boot_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """断电残留：lifespan 启动前批次对账 PROCESSING + INDEXING 脏状态。

    - processing / pending orphans → failed + PROCESS_ORPHANED
    - indexing zombies → ready_with_warnings + rag_indexing_stuck_timeout
    """
    stale = datetime.now(UTC) - timedelta(hours=2)
    await _put_stale_processing("chaos-proc-zombie", updated_at=stale)
    await _put_stale_indexing("chaos-idx-zombie", started_at=stale)

    monkeypatch.setattr(
        "backend.startup.profile_validation.probe_reranker_connectivity",
        AsyncMock(),
    )
    from tests.helpers.lifespan_stubs import stub_lifespan_rag_wiring

    stub_lifespan_rag_wiring(monkeypatch)

    from backend.main import create_app, lifespan

    app = create_app()
    async with lifespan(app):
        proc = await get_pipeline_repository().get_latest("chaos-proc-zombie")
        assert proc is not None
        assert proc.status == PaperStatus.FAILED
        assert proc.error_code == PROCESS_ORPHANED_CODE

        idx = await get_pipeline_repository().get_latest("chaos-idx-zombie")
        assert idx is not None
        assert idx.status == PaperStatus.READY_WITH_WARNINGS
        assert RAG_INDEXING_STUCK_WARNING in idx.extract_warnings


@pytest.mark.asyncio
async def test_http_delete_maps_chroma_partition_to_503_not_500(
    persistence_env,
) -> None:
    """外部向量库分区：DELETE 不得 500，必须映射 VECTOR_STORE_UNAVAILABLE (503)。"""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    import fitz
    from backend.graph.state import STAGE_PERCENT as _SP
    from backend.main import app
    from backend.repositories.paper_repository import PaperRepository
    from backend.repositories.pipeline_repository import PipelineRepository
    from backend.schemas.paper import PaperStatusData as _PSD
    from httpx import ASGITransport, AsyncClient

    paper_id = "chaos-chroma-partition"
    upload_dir = Path(persistence_env["upload_dir"])
    pdf_path = upload_dir / f"{paper_id}.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "chaos partition pdf")
    doc.save(str(pdf_path))
    doc.close()

    await PaperRepository().create(paper_id, "chaos", str(pdf_path), status=PaperStatus.READY)
    await PipelineRepository().save_status(
        paper_id,
        _PSD(
            paper_id=paper_id,
            status=PaperStatus.READY,
            percent=_SP[PipelineStage.READY],
            stage=PipelineStage.READY,
            message="ready",
            updated_at=_dt.now(_UTC),
        ),
    )

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock(side_effect=ConnectionError("chroma killed"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "backend.services.paper_delete_service._resolve_vector_store",
            return_value=vector_store,
        ):
            response = await client.delete(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 503
    assert response.status_code != 500
    body = response.json()
    assert body["error"]["code"] == "VECTOR_STORE_UNAVAILABLE"
    # SQL must remain (hard-fail invariant — no ghost host wipe).
    assert await PaperRepository().get(paper_id) is not None
    assert pdf_path.is_file()


@pytest.mark.architecture_evolution
@pytest.mark.skip(reason="Needs Testcontainers: physical kill of Chroma/Redis mid-flight + reconnect pool")
def test_testcontainers_kill_chroma_midflight_then_reconnect_drain() -> None:
    """Chaos: kill Chroma container mid-task; no HTTP 500; exponential backoff reconnect drains backlog."""
    raise AssertionError("unreachable until Testcontainers chroma/redis harness lands")
