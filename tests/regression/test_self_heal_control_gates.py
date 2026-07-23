# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Regression boundary gates: cold-boot heal / force reextract / cascading DELETE.

These three named assertions lock the V2 self-heal + control escape hatches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from backend.config import get_settings
from backend.db.base import get_async_session_factory
from backend.db.models import PaperRow, PipelineRunRow
from backend.graph.state import STAGE_PERCENT
from backend.graph.store import GraphStore
from backend.pipeline.processing_watchdog import (
    PROCESS_ORPHANED_CODE,
    reset_processing_watchdog_sync_engine,
    stop_processing_watchdog,
)
from backend.rag.models import PaperChunk
from backend.rag.vector_store import VectorStore
from backend.repositories.async_bridge import run_async
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_delete_service import get_paper_delete_service
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient
from tests.helpers.persistence_testkit import (
    init_isolated_database,
    register_test_paper,
    reset_persistence_singletons,
    restart_paper_service,
)


class _FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(ord(c) for c in text) % 97)] for text in texts]


@pytest.fixture
def boot_heal_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "boot_heal.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    monkeypatch.setenv("PROCESS_WATCHDOG_ENABLED", "true")
    monkeypatch.setenv("PROCESS_ORPHAN_GRACE_SECONDS", "10")
    monkeypatch.setenv("RAG_INDEXING_WATCHDOG_ENABLED", "false")
    get_settings.cache_clear()
    reset_persistence_singletons()
    reset_processing_watchdog_sync_engine()
    stop_processing_watchdog()
    run_async(init_isolated_database(db_path))
    yield
    stop_processing_watchdog()
    reset_processing_watchdog_sync_engine()
    reset_persistence_singletons()
    get_settings.cache_clear()


@pytest.fixture
async def control_api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "control_api.db"
    upload_path = tmp_path / "uploads"
    graph_path = tmp_path / "graphs"
    upload_path.mkdir(parents=True, exist_ok=True)
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "false")
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_persistence_singletons()
    await init_isolated_database(db_path)
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, upload_path, graph_path
    reset_persistence_singletons()
    get_settings.cache_clear()


def _make_pdf(upload_dir: Path, name: str) -> Path:
    pdf_path = upload_dir / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "control-gate sample pdf")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


async def _seed_processing(paper_id: str, pdf_path: Path) -> None:
    await PaperRepository().create(
        paper_id,
        "control reextract",
        str(pdf_path),
        status=PaperStatus.PROCESSING,
    )
    await PipelineRepository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PROCESSING,
            percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
            stage=PipelineStage.EXTRACTING,
            message="extracting",
            updated_at=datetime.now(UTC),
        ),
    )


@pytest.mark.asyncio
async def test_boot_reconciliation_processing(
    boot_heal_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cold-boot lifespan must tombstone stale PROCESSING zombies as PROCESS_ORPHANED.

    ``updated_at`` is aged past ``PROCESS_ORPHAN_GRACE_SECONDS`` so rolling-update
    grace does not spare the row (fresh in-ε work is intentionally left alone).
    """
    paper_id = "boot-proc-orphan"
    stale = datetime.now(UTC) - timedelta(hours=2)
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
        run.updated_at = stale
        paper.updated_at = stale
        paper.status = PaperStatus.PROCESSING.value
        await session.commit()

    monkeypatch.setattr(
        "backend.startup.profile_validation.probe_reranker_connectivity",
        AsyncMock(),
    )
    from tests.helpers.lifespan_stubs import stub_lifespan_rag_wiring

    stub_lifespan_rag_wiring(monkeypatch)

    from backend.main import create_app, lifespan

    app = create_app()
    async with lifespan(app):
        latest = await get_pipeline_repository().get_latest(paper_id)
        assert latest is not None
        assert latest.status == PaperStatus.FAILED
        assert latest.error_code == PROCESS_ORPHANED_CODE
        paper_row = await PaperRepository().get(paper_id)
        assert paper_row is not None
        assert paper_row.status == PaperStatus.FAILED


@pytest.mark.asyncio
async def test_force_reextract_overrides_409(control_api_env) -> None:
    """PROCESSING without force → 409; ``?force=true`` → 200 and DB back to pending."""
    client, upload_path, _graph = control_api_env
    paper_id = "gate-reextract-force"
    pdf = _make_pdf(upload_path, f"{paper_id}.pdf")
    await _seed_processing(paper_id, pdf)
    get_paper_service.cache_clear()

    blocked = await client.post(f"/api/v1/papers/{paper_id}/reextract")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PAPER_ALREADY_PROCESSING"

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline", AsyncMock()),
        patch(
            "backend.services.reextract_service.resolve_vector_store_for_delete",
            return_value=AsyncMock(delete_by_paper=AsyncMock()),
        ),
        patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler,
    ):
        forced = await client.post(f"/api/v1/papers/{paper_id}/reextract?force=true")

    assert forced.status_code == 200
    assert forced.json()["data"]["status"] == "pending"
    scheduler.assert_called_once()

    paper_row = await PaperRepository().get(paper_id)
    assert paper_row is not None
    assert paper_row.status == PaperStatus.PENDING
    pipeline = await PipelineRepository().get_latest(paper_id)
    assert pipeline is not None
    assert pipeline.status == PaperStatus.PENDING


@pytest.mark.asyncio
async def test_cascading_delete_removes_all_traces(
    persistence_env,
    tmp_path: Path,
) -> None:
    """READY DELETE must wipe SQL + ``{paper_id}.json`` + Chroma chunks for that paper_id."""
    paper_id = "cascade-trace-001"
    upload_dir = Path(persistence_env["upload_dir"])
    graph_dir = Path(persistence_env["graph_dir"])
    pdf_path = _make_pdf(upload_dir, f"{paper_id}.pdf")

    await PaperRepository().create(
        paper_id,
        "cascade traces",
        str(pdf_path),
        status=PaperStatus.READY,
    )
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

    await restart_paper_service()
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    GraphStore().save(graph)
    graph_json = graph_dir / f"{paper_id}.json"
    assert graph_json.is_file()

    chroma_path = tmp_path / "cascade_chroma"
    store = VectorStore(
        embedding_client=_FakeEmbeddingClient(),
        chroma_path=str(chroma_path),
    )
    await store.index_chunks(
        [
            PaperChunk(
                chunk_id=f"{paper_id}:chunk:0",
                paper_id=paper_id,
                text="cascade delete must erase this chunk",
                section="methods",
                chunk_index=0,
                source="pymupdf",
                char_start=0,
                char_end=40,
            ),
            PaperChunk(
                chunk_id=f"{paper_id}:chunk:1",
                paper_id=paper_id,
                text="second chunk for residual leak detection",
                section="results",
                chunk_index=1,
                source="pymupdf",
                char_start=40,
                char_end=90,
            ),
        ]
    )
    before = store._chunk_collection.get(where={"paper_id": paper_id}, include=[])
    assert len(before.get("ids") or []) == 2

    await get_paper_delete_service().delete(paper_id, force=False, vector_store=store)

    assert await PaperRepository().get(paper_id) is None
    assert await PipelineRepository().get_latest(paper_id) is None
    assert not graph_json.exists()
    assert GraphStore().load(paper_id) is None

    after = store._chunk_collection.get(where={"paper_id": paper_id}, include=[])
    assert len(after.get("ids") or []) == 0
