# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Side-effect audits for first-class delete / re-extract services.

Controlled single-step integration: construct ``PaperDeleteService`` /
``ReextractService`` with real injected repositories, trigger once, then assert
every collaborator footprint (SQL / pipeline ephemeral / PDF / Chroma / status).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from backend.graph.head_store import HeadStore
from backend.graph.state import STAGE_PERCENT
from backend.graph.store import GraphStore
from backend.rag.models import PaperChunk
from backend.rag.vector_store import VectorStore
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_delete_service import PaperDeleteService
from backend.services.paper_pipeline_ops import PaperPipelineOpsService
from backend.services.reextract_service import ReextractService
from tests.helpers.persistence_testkit import restart_paper_service


class _FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(ord(c) for c in text) % 97)] for text in texts]


def _make_pdf(upload_dir: Path, name: str) -> Path:
    pdf_path = upload_dir / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "lifecycle side-effect audit pdf")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _chroma_chunk_count(store: VectorStore, paper_id: str) -> int:
    result = store._chunk_collection.get(where={"paper_id": paper_id}, include=[])
    return len(result.get("ids") or [])


def _minimal_graph(paper_id: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
    )


async def _seed_terminal_ready(
    *,
    paper_id: str,
    pdf_path: Path,
    with_ephemeral: bool = True,
) -> tuple[PaperRepository, PaperPipelineOpsService, PipelineRepository]:
    """Seed a READY terminal paper with optional pipeline ephemeral residue."""
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    pipeline_ops = PaperPipelineOpsService(pipeline_repo)

    await paper_repo.create(paper_id, "side-effect audit", str(pdf_path), status=PaperStatus.READY)
    await pipeline_repo.save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            stage=PipelineStage.READY,
            message="ready",
            updated_at=datetime.now(UTC),
            preview_available=True,
        ),
    )
    GraphStore().save(_minimal_graph(paper_id))
    HeadStore().save(paper_id, merged=IngestHead(title="T", abstract="A", intro="I"))

    if with_ephemeral:
        await pipeline_repo.save_preview_graph(paper_id, _minimal_graph(paper_id))
        await pipeline_repo.set_active_rag_run_id(paper_id, "audit-run-stale")
        await pipeline_repo.begin_pipeline_generation(paper_id)
        assert await pipeline_repo.get_preview_graph(paper_id) is not None
        assert await pipeline_repo.get_active_rag_run_id(paper_id) == "audit-run-stale"
        assert await pipeline_ops.get_pipeline_generation_id(paper_id) is not None

    await restart_paper_service()
    # Re-bind after singleton reset so the service under test shares live repos.
    paper_repo = PaperRepository()
    pipeline_repo = PipelineRepository()
    pipeline_ops = PaperPipelineOpsService(pipeline_repo)
    return paper_repo, pipeline_ops, pipeline_repo


@pytest.mark.asyncio
async def test_delete_service_clears_sql_ephemeral_pdf_and_chroma(
    persistence_env,
    tmp_path: Path,
) -> None:
    """PaperDeleteService must wipe every collaborator footprint in one cascade."""
    paper_id = "audit-delete-side-effects"
    pdf_path = _make_pdf(Path(persistence_env["upload_dir"]), f"{paper_id}.pdf")
    paper_repo, pipeline_ops, pipeline_repo = await _seed_terminal_ready(
        paper_id=paper_id,
        pdf_path=pdf_path,
    )

    store = VectorStore(
        embedding_client=_FakeEmbeddingClient(),
        chroma_path=str(tmp_path / "audit_delete_chroma"),
    )
    await store.index_chunks(
        [
            PaperChunk(
                chunk_id=f"{paper_id}:c0",
                paper_id=paper_id,
                text="embedding must vanish with delete",
                section="body",
                chunk_index=0,
                source="pymupdf",
                char_start=0,
                char_end=30,
            )
        ]
    )
    assert _chroma_chunk_count(store, paper_id) == 1
    assert pdf_path.is_file()

    service = PaperDeleteService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)
    await service.delete(paper_id, force=False, vector_store=store)

    # SQL metadata gone.
    assert await paper_repo.get(paper_id) is None
    assert await pipeline_repo.get_latest(paper_id) is None

    # Pipeline ephemeral / ops state cannot linger without a row (zero footprint).
    assert await pipeline_repo.get_preview_graph(paper_id) is None
    assert await pipeline_repo.get_active_rag_run_id(paper_id) is None
    assert await pipeline_ops.get_pipeline_generation_id(paper_id) is None

    # Physical PDF unlinked; graph/head artefacts removed.
    assert pdf_path.exists() is False
    assert GraphStore().load(paper_id) is None
    assert HeadStore().load(paper_id) is None

    # Chroma embeddings cascaded away.
    assert _chroma_chunk_count(store, paper_id) == 0


@pytest.mark.asyncio
async def test_reextract_service_resets_terminal_pipeline_to_pending(
    persistence_env,
    tmp_path: Path,
) -> None:
    """ReextractService must clone-clean a terminal READY paper back to PENDING."""
    paper_id = "audit-reextract-side-effects"
    pdf_path = _make_pdf(Path(persistence_env["upload_dir"]), f"{paper_id}.pdf")
    paper_repo, pipeline_ops, pipeline_repo = await _seed_terminal_ready(
        paper_id=paper_id,
        pdf_path=pdf_path,
    )

    store = VectorStore(
        embedding_client=_FakeEmbeddingClient(),
        chroma_path=str(tmp_path / "audit_reextract_chroma"),
    )
    await store.index_chunks(
        [
            PaperChunk(
                chunk_id=f"{paper_id}:c0",
                paper_id=paper_id,
                text="stale embedding cleared before requeue",
                section="body",
                chunk_index=0,
                source="pymupdf",
                char_start=0,
                char_end=30,
            )
        ]
    )
    assert _chroma_chunk_count(store, paper_id) == 1
    assert (await paper_repo.get(paper_id)).status == PaperStatus.READY

    service = ReextractService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    with (
        patch("backend.services.reextract_service.abort_in_flight_pipeline"),
        patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler,
    ):
        snapshot = await service.force_reextract(paper_id, force=False, vector_store=store)

    # Status machine reset to initial PENDING / clone-clean.
    assert snapshot.status == PaperStatus.PENDING
    assert snapshot.percent == 0
    assert snapshot.stage is None
    assert snapshot.preview_available is False
    assert snapshot.extract_warnings == []
    assert snapshot.classify_warnings == []
    assert snapshot.head_refine_warnings == []
    assert snapshot.error_code is None

    paper = await paper_repo.get(paper_id)
    assert paper is not None
    assert paper.status == PaperStatus.PENDING
    assert paper.preview_available is False

    pipeline = await pipeline_repo.get_latest(paper_id)
    assert pipeline is not None
    assert pipeline.status == PaperStatus.PENDING
    assert pipeline.percent == 0

    # Ephemeral pipeline residue wiped; PDF retained for the next parse.
    assert await pipeline_repo.get_preview_graph(paper_id) is None
    assert await pipeline_repo.get_active_rag_run_id(paper_id) is None
    assert await pipeline_ops.get_pipeline_generation_id(paper_id) is None
    assert pdf_path.is_file()
    assert GraphStore().load(paper_id) is None
    assert HeadStore().load(paper_id) is None
    assert _chroma_chunk_count(store, paper_id) == 0
    scheduler.assert_called_once_with(paper_id, pdf_path)
