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
    token = svc.begin_pipeline_generation(paper_id)
    assert_pipeline_generation_writable(paper_id, token)


@pytest.mark.asyncio
async def test_assert_writable_rejects_after_watchdog_invalidates(gen_guard_db) -> None:
    paper_id = "gen-zombie"
    await _put_processing(paper_id)
    svc = get_paper_service()
    orphan_token = svc.begin_pipeline_generation(paper_id)
    flipped = fail_orphaned_pipeline_row_sync(
        paper_id,
        error_code=PROCESS_TIMEOUT_CODE,
        message=PROCESS_TIMEOUT_MESSAGE,
    )
    assert flipped
    assert svc.get_pipeline_generation_id(paper_id) is None

    with pytest.raises(ObsoletePipelineGenerationError) as exc_info:
        assert_pipeline_generation_writable(paper_id, orphan_token)
    assert exc_info.value.code == OBSOLETE_PIPELINE_GENERATION_CODE


@pytest.mark.asyncio
async def test_finalize_refuses_graph_write_when_generation_obsolete(gen_guard_db) -> None:
    paper_id = "gen-no-write"
    await _put_processing(paper_id, stage=PipelineStage.STORING)
    svc = get_paper_service()
    orphan_token = svc.begin_pipeline_generation(paper_id)
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
        completion.finalize(
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
async def test_obsolete_run_id_write_blocked(gen_guard_db) -> None:
    """Time-traveling chaos: frozen Run_A cannot dirty GraphStore / SQL after Run_B remints."""
    paper_id = "paper-x-orphan-run"
    await _put_processing(paper_id, stage=PipelineStage.EXTRACTING)
    svc = get_paper_service()

    # 1) Normal extract generation Run_A while PROCESSING.
    run_a = svc.begin_pipeline_generation(paper_id)
    assert svc.get_pipeline_generation_id(paper_id) == run_a
    assert (await svc.get_status(paper_id)).status == PaperStatus.PROCESSING

    # Freeze Run_A just before terminal write (zombie mid-LLM, still holding Run_A token).
    thaw_run_a = asyncio.Event()

    async def _run_a_ghost_finalize(
        *,
        persistence: MagicMock,
        completion: PipelineCompletionService,
    ) -> None:
        await thaw_run_a.wait()
        completion.finalize(
            paper_id,
            graph_data=_minimal_graph(paper_id).model_dump(mode="json"),
            classification_data=_minimal_classification().model_dump(mode="json"),
            pipeline_generation_id=run_a,
        )

    save = MagicMock()
    persistence = MagicMock()
    persistence.save = save
    completion = PipelineCompletionService(graph_persistence=persistence)
    ghost = asyncio.create_task(
        _run_a_ghost_finalize(persistence=persistence, completion=completion),
        name="ghost-run-a-finalize",
    )
    await asyncio.sleep(0)

    # 2) Bypass in-memory Task check: watchdog SQL tombstone + generation invalidate.
    flipped = fail_orphaned_pipeline_row_sync(
        paper_id,
        error_code=PROCESS_TIMEOUT_CODE,
        message=PROCESS_TIMEOUT_MESSAGE,
    )
    assert flipped
    dead = await svc.get_status(paper_id)
    assert dead.status == PaperStatus.FAILED
    assert dead.error_code == PROCESS_TIMEOUT_CODE
    assert svc.get_pipeline_generation_id(paper_id) is None

    # 3) Emergency reextract mint (generation SSOT path used by force reextract after reset).
    # Full HTTP force_reextract is covered elsewhere; here we exercise the production
    # generation + status boundary that late Run_A must not clobber.
    svc.reset_pipeline_for_reextract(paper_id, message="强制重新抽取")
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
    run_b = svc.begin_pipeline_generation(paper_id)
    assert run_b != run_a
    assert svc.get_pipeline_generation_id(paper_id) == run_b
    run_b_before = await svc.get_status(paper_id)
    assert run_b_before.status == PaperStatus.PROCESSING
    assert run_b_before.message == "Run_B ingesting"
    assert run_b_before.error_code is None

    # 4) Thaw Run_A: late GraphStore.save + promote-ready must hard-fail at generation gate.
    thaw_run_a.set()
    with pytest.raises(ObsoletePipelineGenerationError) as exc_info:
        await ghost
    assert exc_info.value.code == OBSOLETE_PIPELINE_GENERATION_CODE
    assert exc_info.value.expected_generation_id == run_a
    assert exc_info.value.current_generation_id == run_b
    save.assert_not_called()

    # 5) Run_B progress must be uncontaminated — no READY flip, generation stays Run_B.
    after = await svc.get_status(paper_id)
    assert after.status == PaperStatus.PROCESSING
    assert after.message == "Run_B ingesting"
    assert after.error_code is None
    assert after.stage == PipelineStage.INGESTING
    assert svc.get_pipeline_generation_id(paper_id) == run_b


@pytest.mark.asyncio
async def test_finalize_refuses_after_reextract_mints_new_generation(gen_guard_db) -> None:
    paper_id = "gen-reextract"
    await _put_processing(paper_id)
    svc = get_paper_service()
    orphan_token = svc.begin_pipeline_generation(paper_id)
    svc.reset_pipeline_for_reextract(paper_id, message="强制重抽")
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
    new_token = svc.begin_pipeline_generation(paper_id)
    assert new_token != orphan_token

    save = MagicMock()
    persistence = MagicMock()
    persistence.save = save
    completion = PipelineCompletionService(graph_persistence=persistence)

    with pytest.raises(ObsoletePipelineGenerationError):
        completion.finalize(
            paper_id,
            graph_data=_minimal_graph(paper_id).model_dump(mode="json"),
            classification_data=_minimal_classification().model_dump(mode="json"),
            pipeline_generation_id=orphan_token,
        )
    save.assert_not_called()
