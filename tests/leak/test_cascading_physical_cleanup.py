# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Cascading physical cleanup — prevent distributed resource leaks on DELETE.

Physical verification matrix (after ``DELETE /papers/{id}`` commits):

1. Relational DB — ``papers`` + ``pipeline_runs`` row counts for paper_id == 0
2. Disk / object store — ``{id}.pdf``, ``{id}.json``, ``{id}.head.json``, sidecars gone
3. Vector store — Chroma ``.get(where={"paper_id": id})`` returns 0 ids on all collections
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from backend.db.base import get_async_session_factory
from backend.db.models import PaperRow, PipelineRunRow
from backend.graph.head_store import HeadStore
from backend.graph.state import STAGE_PERCENT
from backend.graph.store import GraphStore
from backend.rag.models import PaperChunk, PaperEntity, PaperRelation
from backend.rag.vector_store import VectorStore
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.paper_delete_service import get_paper_delete_service
from sqlalchemy import func, select
from tests.helpers.persistence_testkit import restart_paper_service


class _FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(sum(ord(c) for c in text) % 97)] for text in texts]


def _make_pdf(upload_dir: Path, name: str) -> Path:
    pdf_path = upload_dir / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "leak-cascade sample pdf")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _chroma_id_count(collection: object, paper_id: str) -> int:
    result = collection.get(where={"paper_id": paper_id}, include=[])  # type: ignore[attr-defined]
    return len(result.get("ids") or [])


async def _sql_row_counts(paper_id: str) -> tuple[int, int]:
    async with get_async_session_factory()() as session:
        papers = await session.scalar(select(func.count()).select_from(PaperRow).where(PaperRow.paper_id == paper_id))
        runs = await session.scalar(
            select(func.count()).select_from(PipelineRunRow).where(PipelineRunRow.paper_id == paper_id)
        )
    return int(papers or 0), int(runs or 0)


async def _seed_ready_with_artefacts(
    *,
    paper_id: str,
    pdf_path: Path,
    graph_dir: Path,
) -> tuple[Path, Path, Path]:
    await PaperRepository().create(
        paper_id,
        "leak cascade",
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
    service = await restart_paper_service()
    GraphStore().save(
        UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
            edges=[GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF")],
        )
    )
    HeadStore().save(paper_id, merged=IngestHead(title="T", abstract="A", intro="I"))
    await service.save_preview_graph(
        paper_id,
        UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="论点", type="Thesis")],
            edges=[],
        ),
    )
    await service.mark_preview_available(paper_id)

    graph_json = graph_dir / f"{paper_id}.json"
    head_json = graph_dir / f"{paper_id}.head.json"
    sidecar = graph_dir / f"{paper_id}_chunk.cache"
    sidecar.write_text("stale-sidecar", encoding="utf-8")
    assert pdf_path.is_file()
    assert graph_json.is_file()
    assert head_json.is_file()
    assert sidecar.is_file()
    return graph_json, head_json, sidecar


@pytest.mark.asyncio
async def test_cascading_delete_physical_verification_matrix(
    persistence_env,
    tmp_path: Path,
) -> None:
    """Cross-layer Physical Verification after cascading DELETE (zero footprint)."""
    victim_id = "leak-victim-001"
    neighbor_id = "leak-neighbor-002"
    upload_dir = Path(persistence_env["upload_dir"])
    graph_dir = Path(persistence_env["graph_dir"])

    victim_pdf = _make_pdf(upload_dir, f"{victim_id}.pdf")
    neighbor_pdf = _make_pdf(upload_dir, f"{neighbor_id}.pdf")
    graph_json, head_json, sidecar = await _seed_ready_with_artefacts(
        paper_id=victim_id,
        pdf_path=victim_pdf,
        graph_dir=graph_dir,
    )
    await _seed_ready_with_artefacts(
        paper_id=neighbor_id,
        pdf_path=neighbor_pdf,
        graph_dir=graph_dir,
    )

    store = VectorStore(
        embedding_client=_FakeEmbeddingClient(),
        chroma_path=str(tmp_path / "leak_chroma"),
    )
    await store.index_chunks(
        [
            PaperChunk(
                chunk_id=f"{victim_id}:c0",
                paper_id=victim_id,
                text="victim chunk must disappear",
                section="methods",
                chunk_index=0,
                source="pymupdf",
                char_start=0,
                char_end=20,
            ),
            PaperChunk(
                chunk_id=f"{victim_id}:c1",
                paper_id=victim_id,
                text="second victim chunk",
                section="results",
                chunk_index=1,
                source="pymupdf",
                char_start=20,
                char_end=40,
            ),
            PaperChunk(
                chunk_id=f"{neighbor_id}:c0",
                paper_id=neighbor_id,
                text="neighbor chunk must survive",
                section="methods",
                chunk_index=0,
                source="pymupdf",
                char_start=0,
                char_end=20,
            ),
        ]
    )
    await store.index_entities(
        [
            PaperEntity(
                entity_id=f"{victim_id}:e0",
                paper_id=victim_id,
                label="VictimEntity",
                node_type="Concept",
                description="must be purged with paper",
            )
        ]
    )
    await store.index_relations(
        [
            PaperRelation(
                relation_id=f"{victim_id}:r0",
                paper_id=victim_id,
                source_id=f"{victim_id}:e0",
                target_id=f"{victim_id}:e0",
                relation_type="RELATED",
                description="must be purged with paper",
            )
        ]
    )

    assert _chroma_id_count(store._chunk_collection, victim_id) == 2
    assert _chroma_id_count(store._entity_collection, victim_id) == 1
    assert _chroma_id_count(store._relation_collection, victim_id) == 1
    assert await _sql_row_counts(victim_id) == (1, 1)

    await restart_paper_service()
    await get_paper_delete_service().delete(victim_id, force=False, vector_store=store)

    # --- 1. Relational DB ---
    paper_count, run_count = await _sql_row_counts(victim_id)
    assert paper_count == 0
    assert run_count == 0
    assert await PaperRepository().get(victim_id) is None
    assert await PipelineRepository().get_latest(victim_id) is None

    # Neighbor must not be collateral damage.
    assert await _sql_row_counts(neighbor_id) == (1, 1)

    # --- 2. Physical disk ---
    assert victim_pdf.exists() is False
    assert graph_json.exists() is False
    assert head_json.exists() is False
    assert sidecar.exists() is False
    assert GraphStore().load(victim_id) is None
    assert HeadStore().load(victim_id) is None
    # Alias check: product uses ``{id}.json`` (not ``{id}_graph.json``).
    assert not (graph_dir / f"{victim_id}_graph.json").exists()
    assert neighbor_pdf.is_file()
    assert (graph_dir / f"{neighbor_id}.json").is_file()

    # --- 3. Vector store (raw Chroma get) ---
    assert _chroma_id_count(store._chunk_collection, victim_id) == 0
    assert _chroma_id_count(store._entity_collection, victim_id) == 0
    assert _chroma_id_count(store._relation_collection, victim_id) == 0
    assert _chroma_id_count(store._chunk_collection, neighbor_id) == 1


@pytest.mark.asyncio
async def test_http_delete_triggers_same_physical_invariants(
    persistence_env,
    tmp_path: Path,
) -> None:
    """HTTP ``DELETE /api/v1/papers/{id}`` must satisfy the same three-layer matrix."""
    from backend.main import app
    from httpx import ASGITransport, AsyncClient

    paper_id = "leak-http-001"
    upload_dir = Path(persistence_env["upload_dir"])
    graph_dir = Path(persistence_env["graph_dir"])
    pdf_path = _make_pdf(upload_dir, f"{paper_id}.pdf")
    graph_json, head_json, sidecar = await _seed_ready_with_artefacts(
        paper_id=paper_id,
        pdf_path=pdf_path,
        graph_dir=graph_dir,
    )

    store = VectorStore(
        embedding_client=_FakeEmbeddingClient(),
        chroma_path=str(tmp_path / "leak_http_chroma"),
    )
    await store.index_chunks(
        [
            PaperChunk(
                chunk_id=f"{paper_id}:c0",
                paper_id=paper_id,
                text="http delete victim chunk",
                section="body",
                chunk_index=0,
                source="pymupdf",
                char_start=0,
                char_end=10,
            )
        ]
    )
    assert _chroma_id_count(store._chunk_collection, paper_id) == 1

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "backend.services.paper_delete_service._resolve_vector_store",
            return_value=store,
        ):
            response = await client.delete(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 204
    assert response.content == b""

    assert await _sql_row_counts(paper_id) == (0, 0)
    assert pdf_path.exists() is False
    assert graph_json.exists() is False
    assert head_json.exists() is False
    assert sidecar.exists() is False
    assert _chroma_id_count(store._chunk_collection, paper_id) == 0
