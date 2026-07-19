# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Pipeline generation write-guard: refuse obsolete finalize after kill / reextract."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from backend.config import get_settings
from backend.graph.state import STAGE_PERCENT
from backend.repositories.async_bridge import run_async
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.repositories.pipeline_sync import (
    fail_orphaned_pipeline_row_sync,
    reset_pipeline_sync_engine,
)
from backend.schemas.graph import GraphNode, NodeType, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import (
    OBSOLETE_PIPELINE_GENERATION_CODE,
    PROCESS_TIMEOUT_CODE,
    PROCESS_TIMEOUT_MESSAGE,
    ObsoletePipelineGenerationError,
)
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import PipelineCompletionService
from backend.services.pipeline_generation_guard import assert_pipeline_generation_writable
from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_test_paper,
    reset_persistence_singletons,
)


@pytest.fixture
def gen_guard_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "pipeline_generation_guard.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    get_settings.cache_clear()
    reset_persistence_singletons()
    reset_pipeline_sync_engine()
    run_async(init_isolated_database(db_path))
    yield
    reset_pipeline_sync_engine()
    reset_persistence_singletons()
    get_settings.cache_clear()


def _minimal_graph(paper_id: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        title="gen-guard",
        paradigm=Paradigm.STEM,
        nodes=[GraphNode(id="n1", label="q", type=NodeType.RESEARCH_QUESTION)],
        edges=[],
        summary="pipeline generation guard",
    )


def _minimal_classification() -> ParadigmClassification:
    return ParadigmClassification(paradigm=Paradigm.STEM, confidence=0.9, reason="test")


async def _put_processing(paper_id: str, *, stage: PipelineStage = PipelineStage.EXTRACTING) -> None:
    await register_test_paper(paper_id, status=PaperStatus.PENDING, with_status_row=True)
    await get_pipeline_repository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PROCESSING,
            percent=STAGE_PERCENT[stage],
            stage=stage,
            message="processing",
            updated_at=datetime.now(UTC),
        ),
    )


@pytest.mark.asyncio
async def test_assert_writable_allows_matching_generation(gen_guard_db) -> None:
    paper_id = "gen-ok"
    await _put_processing(paper_id)
    svc = get_paper_service()
    token = await svc.begin_pipeline_generation(paper_id)
    await assert_pipeline_generation_writable(paper_id, token)


@pytest.mark.asyncio
async def test_assert_writable_rejects_after_watchdog_invalidates(gen_guard_db) -> None:
    paper_id = "gen-zombie"
    await _put_processing(paper_id)
    svc = get_paper_service()
    orphan_token = await svc.begin_pipeline_generation(paper_id)
    flipped = fail_orphaned_pipeline_row_sync(
        paper_id,
        error_code=PROCESS_TIMEOUT_CODE,
        message=PROCESS_TIMEOUT_MESSAGE,
    )
    assert flipped
    assert await svc.get_pipeline_generation_id(paper_id) is None

    with pytest.raises(ObsoletePipelineGenerationError) as exc_info:
        await assert_pipeline_generation_writable(paper_id, orphan_token)
    assert exc_info.value.code == OBSOLETE_PIPELINE_GENERATION_CODE


@pytest.mark.asyncio
async def test_finalize_refuses_graph_write_when_generation_obsolete(gen_guard_db) -> None:
    paper_id = "gen-no-write"
    await _put_processing(paper_id, stage=PipelineStage.STORING)
    svc = get_paper_service()
    orphan_token = await svc.begin_pipeline_generation(paper_id)
    fail_orphaned_pipeline_row_sync(
        paper_id,
        error_code=PROCESS_TIMEOUT_CODE,
        message=PROCESS_TIMEOUT_MESSAGE,
    )

    save = MagicMock()
    persistence = MagicMock()
    persistence.save = save
    completion = PipelineCompletionService(graph_persistence=persistence)
    graph = _minimal_graph(paper_id)
    classification = _minimal_classification()

    with pytest.raises(ObsoletePipelineGenerationError):
        await completion.finalize(
            paper_id,
            graph_data=graph.model_dump(mode="json"),
            classification_data=classification.model_dump(mode="json"),
            pipeline_generation_id=orphan_token,
        )

    save.assert_not_called()
    row = await svc.get_status(paper_id)
    assert row.status == PaperStatus.FAILED
    assert row.error_code == PROCESS_TIMEOUT_CODE


@pytest.mark.asyncio
@pytest.mark.process_release_gate
async def test_obsolete_run_id_write_blocked(gen_guard_db, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Time-traveling chaos: frozen Run_A cannot dirty real GraphStore / SQL after Run_B remints.

    Uses production ``fail_orphaned_pipeline_paper_sync``, ``force_reextract``,
    ``PipelineCompletionService`` + on-disk ``GraphStore`` — not MagicMock persistence.
    """
    from backend.graph.store import GraphStore
    from backend.pipeline.processing_watchdog import PROCESS_TIMEOUT_CODE, PROCESS_TIMEOUT_MESSAGE
    from backend.repositories.paper_repository import get_paper_repository
    from backend.services.graph_persistence_service import GraphPersistenceService
    from backend.services.paper_service import get_paper_service
    from backend.services.reextract_service import force_reextract, reset_reextract_inflight_gate

    reset_reextract_inflight_gate()
    paper_id = "paper-x-orphan-run"
    await _put_processing(paper_id, stage=PipelineStage.EXTRACTING)
    svc = get_paper_service()

    settings = get_settings()
    pdf_path = Path(settings.upload_dir) / f"{paper_id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    await get_paper_repository().update_paths(paper_id, pdf_path=str(pdf_path))

    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    persistence = GraphPersistenceService(store=GraphStore(base_dir=graph_dir))
    completion = PipelineCompletionService(graph_persistence=persistence)
    graph_file = graph_dir / f"{paper_id}.json"

    # 1) Normal extract generation Run_A while PROCESSING.
    run_a = await svc.begin_pipeline_generation(paper_id)
    assert await svc.get_pipeline_generation_id(paper_id) == run_a
    assert (await svc.get_status(paper_id)).status == PaperStatus.PROCESSING

    # Park Run_A at GraphStore.save entrance (before crossing write boundary).
    at_graph_store_entry = asyncio.Event()
    thaw_run_a = asyncio.Event()

    async def _run_a_ghost_finalize() -> None:
        at_graph_store_entry.set()
        await thaw_run_a.wait()
        await completion.finalize(
            paper_id,
            graph_data=_minimal_graph(paper_id).model_dump(mode="json"),
            classification_data=_minimal_classification().model_dump(mode="json"),
            pipeline_generation_id=run_a,
        )

    ghost = asyncio.create_task(_run_a_ghost_finalize(), name="ghost-run-a-finalize")
    await asyncio.wait_for(at_graph_store_entry.wait(), timeout=1.0)
    assert not thaw_run_a.is_set()
    assert not graph_file.is_file()

    # 2) Control-plane death: production sync orphan fail (same SQL as Cascading Kill).
    flipped = svc.fail_orphaned_pipeline_paper_sync(
        paper_id,
        error_code=PROCESS_TIMEOUT_CODE,
        message=PROCESS_TIMEOUT_MESSAGE,
    )
    assert flipped
    dead = await svc.get_status(paper_id)
    assert dead.status == PaperStatus.FAILED
    assert dead.error_code == PROCESS_TIMEOUT_CODE
    assert await svc.get_pipeline_generation_id(paper_id) is None

    # 3) Emergency reextract (?force=true) — real abort/claim/reset; stub only LLM reschedule + Wave2 delay.
    scheduled: list[tuple[str, Path]] = []

    def _spy_schedule(pid: str, path: Path) -> None:
        scheduled.append((pid, path))

    def _spy_wave2(pid: str, targets: object) -> list[object]:
        return []

    class _EmptyVectorStore:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete_by_paper(self, pid: str) -> None:
            self.deleted.append(pid)

    vector_store = _EmptyVectorStore()
    monkeypatch.setattr(
        "backend.services.reextract_service.schedule_paper_pipeline",
        _spy_schedule,
    )
    monkeypatch.setattr(
        "backend.rag.wipe_vector_sweep.schedule_wipe_wave2_sweep",
        _spy_wave2,
    )
    snapshot = await force_reextract(svc, paper_id, force=True, vector_store=vector_store)
    assert snapshot.status == PaperStatus.PENDING
    assert scheduled and scheduled[0][0] == paper_id
    assert vector_store.deleted == [paper_id]

    # Simulate Run_B pipeline start (workflow.begin_pipeline_generation after schedule).
    await get_pipeline_repository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PROCESSING,
            percent=STAGE_PERCENT[PipelineStage.INGESTING],
            stage=PipelineStage.INGESTING,
            message="Run_B ingesting",
            updated_at=datetime.now(UTC),
        ),
    )
    run_b = await svc.begin_pipeline_generation(paper_id)
    assert run_b != run_a
    assert await svc.get_pipeline_generation_id(paper_id) == run_b
    run_b_before = await svc.get_status(paper_id)
    assert run_b_before.status == PaperStatus.PROCESSING
    assert run_b_before.message == "Run_B ingesting"
    assert run_b_before.error_code is None
    run_b_fingerprint = {
        "status": run_b_before.status,
        "stage": run_b_before.stage,
        "message": run_b_before.message,
        "percent": run_b_before.percent,
        "error_code": run_b_before.error_code,
        "generation_id": await svc.get_pipeline_generation_id(paper_id),
    }

    # 4) Thaw ghost Run_A: late GraphStore.save + promote-ready must hard-fail at gate.
    thaw_run_a.set()
    with pytest.raises(ObsoletePipelineGenerationError) as exc_info:
        await ghost
    assert exc_info.value.code == OBSOLETE_PIPELINE_GENERATION_CODE
    assert exc_info.value.expected_generation_id == run_a
    assert exc_info.value.current_generation_id == run_b

    assert not graph_file.is_file()
    after = await svc.get_status(paper_id)
    assert {
        "status": after.status,
        "stage": after.stage,
        "message": after.message,
        "percent": after.percent,
        "error_code": after.error_code,
        "generation_id": await svc.get_pipeline_generation_id(paper_id),
    } == run_b_fingerprint
    assert after.status == PaperStatus.PROCESSING
    assert after.status not in {PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS, PaperStatus.INDEXING}
    assert await svc.get_pipeline_generation_id(paper_id) == run_b

    reset_reextract_inflight_gate()


@pytest.mark.asyncio
async def test_finalize_refuses_after_reextract_mints_new_generation(gen_guard_db) -> None:
    paper_id = "gen-reextract"
    await _put_processing(paper_id)
    svc = get_paper_service()
    orphan_token = await svc.begin_pipeline_generation(paper_id)
    await svc.reset_pipeline_for_reextract(paper_id, message="强制重抽")
    await get_pipeline_repository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PROCESSING,
            percent=STAGE_PERCENT[PipelineStage.INGESTING],
            stage=PipelineStage.INGESTING,
            message="重抽中",
            updated_at=datetime.now(UTC),
        ),
    )
    new_token = await svc.begin_pipeline_generation(paper_id)
    assert new_token != orphan_token

    save = MagicMock()
    persistence = MagicMock()
    persistence.save = save
    completion = PipelineCompletionService(graph_persistence=persistence)

    with pytest.raises(ObsoletePipelineGenerationError):
        await completion.finalize(
            paper_id,
            graph_data=_minimal_graph(paper_id).model_dump(mode="json"),
            classification_data=_minimal_classification().model_dump(mode="json"),
            pipeline_generation_id=orphan_token,
        )
    save.assert_not_called()
