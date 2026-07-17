# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Cascading DELETE /papers/{id} — physical cleanup order and force gate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from backend.api.exceptions import ApiError
from backend.graph.head_store import HeadStore
from backend.graph.state import STAGE_PERCENT
from backend.graph.store import GraphStore
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService
from tests.helpers.persistence_testkit import restart_paper_service


@pytest.fixture
def sample_pdf(persistence_env, tmp_path: Path) -> Path:
    pdf_path = persistence_env["upload_dir"] / "delete-sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample text for delete cascade tests.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


async def _register_paper(
    paper_id: str,
    pdf_path: Path,
    *,
    status: PaperStatus,
) -> None:
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    await paper_repo.create(paper_id, "delete test paper", str(pdf_path), status=status)
    now = datetime.now(UTC)
    if status == PaperStatus.PROCESSING:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
            stage=PipelineStage.EXTRACTING,
            message="extracting",
            updated_at=now,
        )
    elif status == PaperStatus.INDEXING:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=STAGE_PERCENT[PipelineStage.INDEXING],
            stage=PipelineStage.INDEXING,
            message="indexing",
            updated_at=now,
        )
    elif status == PaperStatus.READY:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=STAGE_PERCENT[PipelineStage.READY],
            stage=PipelineStage.READY,
            message="ready",
            updated_at=now,
        )
    else:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=status,
            percent=0,
            stage=None,
            message="pending",
            updated_at=now,
        )
    await pipeline_repo.save_status(paper_id, snapshot)


async def _seed_artefacts(service: PaperService, paper_id: str) -> None:
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )
    GraphStore().save(graph)
    HeadStore().save(paper_id, merged=IngestHead(title="T", abstract="A", intro="I"))
    service.save_preview_graph(paper_id, graph)
    service.mark_preview_available(paper_id)


@pytest.mark.asyncio
async def test_delete_vector_not_found_is_success(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-chroma-404"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock(side_effect=FileNotFoundError("collection missing"))

    with patch(
        "backend.services.paper_delete_service._resolve_vector_store",
        return_value=vector_store,
    ):
        await service.delete_paper(paper_id, force=False)

    assert await PaperRepository().get(paper_id) is None
    assert not sample_pdf.is_file()


@pytest.mark.asyncio
async def test_delete_vector_timeout_hard_fails_without_sql_wipe(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-chroma-503"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()
    await _seed_artefacts(service, paper_id)

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock(side_effect=TimeoutError("chroma timeout"))

    with (
        patch(
            "backend.services.paper_delete_service._resolve_vector_store",
            return_value=vector_store,
        ),
        pytest.raises(ApiError) as exc_info,
    ):
        await service.delete_paper(paper_id, force=False)

    assert exc_info.value.code == "VECTOR_STORE_UNAVAILABLE"
    assert exc_info.value.status_code == 503
    assert await PaperRepository().get(paper_id) is not None
    assert sample_pdf.is_file()
    assert GraphStore().load(paper_id) is not None


@pytest.mark.asyncio
async def test_delete_purges_graph_dir_sidecars(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-sidecar-001"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()
    graph_dir = Path(persistence_env["graph_dir"])
    sidecar = graph_dir / f"{paper_id}_chunk.cache"
    sidecar.write_text("stale", encoding="utf-8")

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()
    with patch(
        "backend.services.paper_delete_service._resolve_vector_store",
        return_value=vector_store,
    ):
        await service.delete_paper(paper_id, force=False)

    assert not sidecar.exists()
    assert await PaperRepository().get(paper_id) is None


@pytest.mark.asyncio
async def test_delete_ready_cascades_sql_graph_pdf_chroma(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-ready-001"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()
    await _seed_artefacts(service, paper_id)
    assert GraphStore().load(paper_id) is not None
    assert sample_pdf.is_file()

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()

    with patch(
        "backend.services.paper_delete_service._resolve_vector_store",
        return_value=vector_store,
    ):
        await service.delete_paper(paper_id, force=False)

    assert await PaperRepository().get(paper_id) is None
    assert await PipelineRepository().get_latest(paper_id) is None
    assert GraphStore().load(paper_id) is None
    assert HeadStore().load(paper_id) is None
    assert not sample_pdf.is_file()
    vector_store.delete_by_paper.assert_awaited_once_with(paper_id)


@pytest.mark.asyncio
async def test_delete_processing_without_force_returns_409(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-processing-409"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.PROCESSING)
    service = await restart_paper_service()

    with pytest.raises(ApiError) as exc_info:
        await service.delete_paper(paper_id, force=False)

    assert exc_info.value.code == "PAPER_ALREADY_PROCESSING"
    assert exc_info.value.status_code == 409
    assert await PaperRepository().get(paper_id) is not None
    assert sample_pdf.is_file()


@pytest.mark.asyncio
async def test_delete_indexing_without_force_returns_409(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-indexing-409"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.INDEXING)
    service = await restart_paper_service()

    with pytest.raises(ApiError) as exc_info:
        await service.delete_paper(paper_id, force=False)

    assert exc_info.value.code == "PAPER_ALREADY_PROCESSING"
    assert exc_info.value.status_code == 409
    assert await PaperRepository().get(paper_id) is not None
    assert sample_pdf.is_file()


@pytest.mark.asyncio
async def test_delete_indexing_with_force_cascades(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-indexing-force"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.INDEXING)
    service = await restart_paper_service()
    await _seed_artefacts(service, paper_id)

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()
    abort = AsyncMock()

    with (
        patch(
            "backend.services.paper_delete_service._resolve_vector_store",
            return_value=vector_store,
        ),
        patch(
            "backend.services.paper_delete_service.abort_in_flight_pipeline",
            abort,
        ),
    ):
        await service.delete_paper(paper_id, force=True)

    abort.assert_awaited_once_with(paper_id)
    assert await PaperRepository().get(paper_id) is None
    assert GraphStore().load(paper_id) is None
    assert not sample_pdf.is_file()
    vector_store.delete_by_paper.assert_awaited_once_with(paper_id)


@pytest.mark.asyncio
async def test_delete_processing_with_force_cascades(
    persistence_env,
    sample_pdf: Path,
) -> None:
    paper_id = "delete-processing-force"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.PROCESSING)
    service = await restart_paper_service()
    await _seed_artefacts(service, paper_id)

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()
    abort = AsyncMock()

    with (
        patch(
            "backend.services.paper_delete_service._resolve_vector_store",
            return_value=vector_store,
        ),
        patch(
            "backend.services.paper_delete_service.abort_in_flight_pipeline",
            abort,
        ),
    ):
        await service.delete_paper(paper_id, force=True)

    abort.assert_awaited_once_with(paper_id)
    assert await PaperRepository().get(paper_id) is None
    assert GraphStore().load(paper_id) is None
    assert not sample_pdf.is_file()
    vector_store.delete_by_paper.assert_awaited_once_with(paper_id)


@pytest.mark.asyncio
async def test_delete_hard_fails_when_pdf_unlink_leaves_residue(
    persistence_env,
    sample_pdf: Path,
) -> None:
    """Disk residue must abort before SQL wipe (zero-footprint contract)."""
    paper_id = "delete-pdf-residue"
    await _register_paper(paper_id, sample_pdf, status=PaperStatus.READY)
    service = await restart_paper_service()
    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()

    def _unlink_fails(_path: str | None) -> bool:
        raise ApiError(
            "DISK_ARTEFACT_DELETE_FAILED",
            "simulated pdf residue",
            status_code=500,
        )

    with (
        patch(
            "backend.services.paper_delete_service._resolve_vector_store",
            return_value=vector_store,
        ),
        patch(
            "backend.services.paper_delete_service.abort_in_flight_pipeline",
            AsyncMock(),
        ),
        patch("backend.services.paper_delete_service._unlink_pdf", side_effect=_unlink_fails),
    ):
        with pytest.raises(ApiError) as exc_info:
            await service.delete_paper(paper_id, force=False)

    assert exc_info.value.code == "DISK_ARTEFACT_DELETE_FAILED"
    assert exc_info.value.status_code == 500
    assert await PaperRepository().get(paper_id) is not None
    assert sample_pdf.is_file()
