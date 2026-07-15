"""Pipeline generation write-guard: refuse obsolete finalize after kill / reextract."""

from __future__ import annotations

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
