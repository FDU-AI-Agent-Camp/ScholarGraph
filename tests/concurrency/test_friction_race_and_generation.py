"""Concurrency & temporal friction tests — reextract race + replace-lock release.

Maps to the full-stack matrix §异步时序验证 (Race / Cancellation).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest
from backend.api.exceptions import ApiError
from backend.graph.state import STAGE_PERCENT
from backend.rag.indexing_run_registry import get_indexing_run_registry
from backend.rag.models import PaperChunk
from backend.rag.vector_store import GENERATION_GUARD_LOG_PREFIX, ObsoleteGenerationWarning, VectorStore
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.reextract_service import (
    force_reextract,
    is_reextract_inflight,
    reset_reextract_inflight_gate,
)
from tests.helpers.persistence_testkit import restart_paper_service
from tests.rag.test_vector_store import FakeCollection, FakeEmbeddingClient


def _make_pdf(upload_dir: Path, name: str) -> Path:
    pdf_path = upload_dir / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "concurrency reextract sample")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


async def _seed_ready(paper_id: str, pdf_path: Path) -> None:
    await PaperRepository().create(paper_id, "race paper", str(pdf_path), status=PaperStatus.READY)
    await PipelineRepository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            stage=PipelineStage.READY,
            message="ready",
            updated_at=datetime.now(UTC),
        ),
    )


@pytest.fixture(autouse=True)
def _clear_reextract_gate() -> None:
    reset_reextract_inflight_gate()
    yield
    reset_reextract_inflight_gate()


@pytest.mark.asyncio
async def test_concurrent_reextract_only_one_wins_nine_get_409(
    persistence_env,
) -> None:
    """Production ``force_reextract`` claim gate under burst: 1 winner, 9× 409.

    Side I/O (abort duration, vector purge, schedule) is stubbed only to hold the
    claim window; DB reset + pending snapshot still run through production code.
    """
    paper_id = "reextract-race-10"
    pdf = _make_pdf(Path(persistence_env["upload_dir"]), f"{paper_id}.pdf")
    await _seed_ready(paper_id, pdf)
    service = await restart_paper_service()

    hold = asyncio.Event()
    entered = asyncio.Event()
    schedule_calls: list[tuple[str, Path]] = []

    async def _slow_abort(_paper_id: str) -> None:
        entered.set()
        await hold.wait()

    def _schedule(pid: str, path: Path) -> None:
        schedule_calls.append((pid, path))

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline", _slow_abort),
        patch(
            "backend.services.reextract_service.resolve_vector_store_for_delete",
            return_value=AsyncMock(delete_by_paper=AsyncMock()),
        ),
        patch("backend.services.reextract_service.schedule_paper_pipeline", _schedule),
    ):
        tasks = [
            asyncio.create_task(force_reextract(service, paper_id, force=False), name=f"rex-{i}") for i in range(10)
        ]
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        await asyncio.sleep(0.05)
        hold.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [item for item in results if not isinstance(item, BaseException)]
    conflicts = [
        item
        for item in results
        if isinstance(item, ApiError) and item.status_code == 409 and item.code == "PAPER_ALREADY_PROCESSING"
    ]
    assert len(successes) == 1
    assert len(conflicts) == 9
    assert len(schedule_calls) == 1
    assert successes[0].status == PaperStatus.PENDING
    assert not is_reextract_inflight(paper_id)

    # Production SQL effects of the single winner (not mock return values).
    paper = await PaperRepository().get(paper_id)
    assert paper is not None
    assert paper.status == PaperStatus.PENDING
    pipeline = await PipelineRepository().get_latest(paper_id)
    assert pipeline is not None
    assert pipeline.status == PaperStatus.PENDING


@pytest.mark.asyncio
async def test_foreign_worker_claim_blocks_reextract(persistence_env) -> None:
    """Simulate another worker's durable claim: local force_reextract must 409."""
    from backend.db.models import PAPER_OPS_OPERATION_REEXTRACT
    from backend.repositories.paper_ops_claim_repository import get_paper_ops_claim_repository

    paper_id = "reextract-foreign-claim"
    pdf = _make_pdf(Path(persistence_env["upload_dir"]), f"{paper_id}.pdf")
    await _seed_ready(paper_id, pdf)
    service = await restart_paper_service()

    await get_paper_ops_claim_repository().seed_claim_for_tests(
        paper_id,
        operation=PAPER_OPS_OPERATION_REEXTRACT,
        owner_token="worker-a-token",
    )
    assert is_reextract_inflight(paper_id)

    with pytest.raises(ApiError) as exc_info:
        await force_reextract(service, paper_id, force=False)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PAPER_ALREADY_PROCESSING"
    assert is_reextract_inflight(paper_id)

    # Foreign owner still holds the row until TTL steal / force eviction.
    released = await get_paper_ops_claim_repository().release(paper_id, "worker-a-token")
    assert released
    assert not is_reextract_inflight(paper_id)


@pytest.mark.asyncio
async def test_delete_and_reextract_share_cluster_mutex(persistence_env) -> None:
    """Delete and reextract must not interleave wipe critical sections for one paper."""
    from backend.db.models import PAPER_OPS_OPERATION_DELETE
    from backend.repositories.paper_ops_claim_repository import get_paper_ops_claim_repository
    from backend.services.paper_delete_service import delete_paper

    paper_id = "wipe-mutex-cross"
    pdf = _make_pdf(Path(persistence_env["upload_dir"]), f"{paper_id}.pdf")
    await _seed_ready(paper_id, pdf)
    service = await restart_paper_service()

    hold = asyncio.Event()
    entered = asyncio.Event()

    async def _slow_abort(_paper_id: str) -> None:
        entered.set()
        await hold.wait()

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline", _slow_abort),
        patch(
            "backend.services.reextract_service.resolve_vector_store_for_delete",
            return_value=AsyncMock(delete_by_paper=AsyncMock()),
        ),
        patch("backend.services.reextract_service.schedule_paper_pipeline"),
    ):
        rex_task = asyncio.create_task(force_reextract(service, paper_id, force=False))
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        assert is_reextract_inflight(paper_id)

        with pytest.raises(ApiError) as exc_info:
            await delete_paper(
                service,
                paper_id,
                force=True,
                vector_store=AsyncMock(delete_by_paper=AsyncMock()),
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "PAPER_ALREADY_PROCESSING"

        hold.set()
        await rex_task

    assert not is_reextract_inflight(paper_id)

    # Symmetric: open delete claim blocks reextract.
    await get_paper_ops_claim_repository().seed_claim_for_tests(
        paper_id,
        operation=PAPER_OPS_OPERATION_DELETE,
        owner_token="delete-owner",
    )
    with pytest.raises(ApiError) as blocked:
        await force_reextract(service, paper_id, force=False)
    assert blocked.value.status_code == 409
    await get_paper_ops_claim_repository().release(paper_id, "delete-owner")


@pytest.mark.asyncio
async def test_expired_cluster_claim_is_stealable(persistence_env) -> None:
    """TTL expiry allows another worker to steal the durable wipe mutex."""
    from backend.db.models import PAPER_OPS_OPERATION_REEXTRACT
    from backend.repositories.paper_ops_claim_repository import get_paper_ops_claim_repository

    paper_id = "claim-steal-ttl"
    repo = get_paper_ops_claim_repository()
    await repo.seed_claim_for_tests(
        paper_id,
        operation=PAPER_OPS_OPERATION_REEXTRACT,
        owner_token="stale-owner",
        ttl_seconds=0.01,
    )
    await asyncio.sleep(0.05)
    token = await repo.try_acquire(paper_id, operation=PAPER_OPS_OPERATION_REEXTRACT)
    assert token != "stale-owner"
    assert await repo.is_held(paper_id)
    await repo.release(paper_id, token)


@pytest.mark.asyncio
async def test_reextract_slot_releases_after_timeout_error(
    persistence_env,
) -> None:
    """TimeoutError mid-flight must still release the claim so a later reextract proceeds."""
    paper_id = "reextract-lock-release"
    pdf = _make_pdf(Path(persistence_env["upload_dir"]), f"{paper_id}.pdf")
    await _seed_ready(paper_id, pdf)
    service = await restart_paper_service()

    async def _boom(_paper_id: str) -> None:
        raise TimeoutError("simulated abort timeout")

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline", _boom),
        patch(
            "backend.services.reextract_service.resolve_vector_store_for_delete",
            return_value=AsyncMock(delete_by_paper=AsyncMock()),
        ),
        patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler,
    ):
        with pytest.raises(TimeoutError):
            await force_reextract(service, paper_id, force=False)
        assert not is_reextract_inflight(paper_id)

        with patch(
            "backend.services.reextract_service.abort_in_flight_pipeline",
            AsyncMock(),
        ):
            snapshot = await force_reextract(service, paper_id, force=False)

    assert snapshot.status == PaperStatus.PENDING
    scheduler.assert_called_once()
    assert not is_reextract_inflight(paper_id)


@pytest.mark.asyncio
async def test_replace_lock_released_after_cancelled_replace() -> None:
    """VectorStore per-paper replace Lock must unlock after CancelledError."""
    get_indexing_run_registry().reset()
    paper_service = MagicMock()
    paper_service.get_active_run_id.return_value = None
    paper_service.set_active_run_id = MagicMock()

    store = VectorStore(
        paper_service=paper_service,
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=FakeCollection(),
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )
    paper_id = "lock-release-paper"
    lock = store._replace_locks.setdefault(paper_id, asyncio.Lock())

    async def _hang_index(*_a, **_k):
        await asyncio.sleep(60)

    with patch.object(store, "_index_chunks", _hang_index):
        task = asyncio.create_task(
            store.replace_paper_index(
                paper_id,
                chunks=[
                    PaperChunk(
                        chunk_id=f"{paper_id}:0",
                        paper_id=paper_id,
                        text="body for lock release",
                        section="body",
                        chunk_index=0,
                        source="pymupdf",
                        char_start=0,
                        char_end=10,
                    )
                ],
                entities=[],
                relations=[],
            )
        )
        await asyncio.sleep(0.05)
        assert lock.locked()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert not lock.locked()

    await asyncio.wait_for(
        store.replace_paper_index(
            paper_id,
            chunks=[
                PaperChunk(
                    chunk_id=f"{paper_id}:1",
                    paper_id=paper_id,
                    text="successor after unlock",
                    section="body",
                    chunk_index=1,
                    source="pymupdf",
                    char_start=0,
                    char_end=10,
                )
            ],
            entities=[],
            relations=[],
        ),
        timeout=2.0,
    )
    assert not lock.locked()
    get_indexing_run_registry().reset()


@pytest.mark.asyncio
async def test_obsolete_generation_warning_on_refuse_activate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Production refuse-activate after sticky revoke → ObsoleteGenerationWarning.

    Simulates cancel/timeout by ``begin`` then ``revoke`` (real registry semantics).
    Does not stub ``may_activate`` or ``_log_generation_guard_abort``.
    """
    caplog.set_level(logging.WARNING)
    get_indexing_run_registry().reset()
    paper_service = MagicMock()
    paper_service.get_active_run_id.return_value = "run_b"
    paper_service.set_active_run_id = MagicMock()
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
        patch("backend.rag.vector_store_replace._generate_run_id", return_value="run_a"),
        patch.object(registry, "begin", side_effect=_begin_then_revoke),
        pytest.warns(ObsoleteGenerationWarning, match="is obsolete"),
    ):
        await store.replace_paper_index(
            "paper-gen-warn",
            chunks=[
                PaperChunk(
                    chunk_id="paper-gen-warn:0",
                    paper_id="paper-gen-warn",
                    text="stale generation body",
                    section="body",
                    chunk_index=0,
                    source="pymupdf",
                    char_start=0,
                    char_end=10,
                )
            ],
            entities=[],
            relations=[],
        )

    assert GENERATION_GUARD_LOG_PREFIX in caplog.text
    paper_service.set_active_run_id.assert_not_called()
    get_indexing_run_registry().reset()
