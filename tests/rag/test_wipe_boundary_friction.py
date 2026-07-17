# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Boundary friction: cluster wipe claim + ghost-vector logical isolation.

Hard proofs for the force-wipe lifecycle (claim ∪ read filter ∪ wave2)::

- ``test_cluster_advisory_lock`` — two DELETE?force≈workers; only one cascades, peer 409
- ``test_ghost_vector_logical_isolation`` — late Run_A in Chroma never reaches HybridRetriever
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest
from backend.api.exceptions import ApiError
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import PaperChunk, QuestionScale
from backend.rag.vector_store import VectorStore
from backend.repositories.paper_repository import PaperRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_delete_service import delete_paper

from tests.helpers.persistence_testkit import register_test_paper, restart_paper_service
from tests.rag.test_vector_store import FakeCollection, FakeEmbeddingClient

RUN_A = "run_a_ghost"
RUN_B = "run_b_active"
GHOST_MARKER = "UNIQUE_GHOST_RUN_A_PAYLOAD_SHOULD_NEVER_SURFACE"
ACTIVE_MARKER = "UNIQUE_ACTIVE_RUN_B_PAYLOAD_VISIBLE"


def _make_pdf(upload_dir: Path, name: str) -> Path:
    pdf_path = upload_dir / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "wipe boundary friction pdf")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _chunk(paper_id: str, text: str, *, chunk_id: str) -> PaperChunk:
    return PaperChunk(
        chunk_id=chunk_id,
        paper_id=paper_id,
        text=text,
        section="body",
        chunk_index=0,
        source="pymupdf",
        char_start=0,
        char_end=len(text),
    )


def _graph(paper_id: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="论点", type="Thesis", data={}),
            GraphNode(id="n2", label="证据", type="Evidence", data={}),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n2",
                target="n1",
                label="SUPPORTS",
                type="SUPPORTS",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_cluster_advisory_lock(persistence_env) -> None:
    """Two concurrent force-DELETE workers: exactly one cascade, peer must 409.

    Simulates multi-worker claim contention via the durable ``paper_ops_claims``
    mutex (SQLite IMMEDIATE / PG advisory on acquire). Side I/O is held only to
    widen the claim window; status reset / SQL delete still run through production.
    """
    paper_id = "cluster-lock-dual-delete"
    pdf = _make_pdf(Path(persistence_env["upload_dir"]), f"{paper_id}.pdf")
    await register_test_paper(
        paper_id,
        status=PaperStatus.READY,
        pdf_path=str(pdf),
    )
    service = await restart_paper_service()

    hold = asyncio.Event()
    entered = asyncio.Event()
    purge_calls: list[str] = []

    async def _slow_abort(_paper_id: str) -> None:
        entered.set()
        await hold.wait()

    async def _tracking_purge(pid: str, *, vector_store: object | None = None) -> bool:
        _ = vector_store
        purge_calls.append(pid)
        return True

    with (
        patch("backend.services.paper_delete_service.abort_in_flight_pipeline", _slow_abort),
        patch(
            "backend.services.paper_delete_service._purge_vector_index_hard",
            _tracking_purge,
        ),
        patch("backend.rag.wipe_vector_sweep.schedule_wipe_wave2_sweep", return_value=[]),
    ):
        worker_a = asyncio.create_task(
            delete_paper(service, paper_id, force=True),
            name="worker-a-force-delete",
        )
        # ≤1ms peer burst — both workers contend for the same durable wipe claim.
        await asyncio.sleep(0.001)
        worker_b = asyncio.create_task(
            delete_paper(service, paper_id, force=True),
            name="worker-b-force-delete",
        )
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        await asyncio.sleep(0.001)
        hold.set()
        results = await asyncio.gather(worker_a, worker_b, return_exceptions=True)

    successes = [item for item in results if not isinstance(item, BaseException)]
    conflicts = [
        item
        for item in results
        if isinstance(item, ApiError) and item.status_code == 409 and item.code == "PAPER_ALREADY_PROCESSING"
    ]
    assert len(successes) == 1, f"expected one cascade winner, got {results!r}"
    assert len(conflicts) == 1, f"expected one 409 peer, got {results!r}"
    assert purge_calls == [paper_id]
    assert await PaperRepository().get(paper_id) is None
    assert not pdf.is_file()


@pytest.mark.asyncio
async def test_ghost_vector_logical_isolation(persistence_env) -> None:
    """Late Run_A upsert must be invisible to HybridRetriever when active is Run_B."""
    paper_id = "ghost-isolation-hybrid"
    await register_test_paper(paper_id, status=PaperStatus.READY)
    service = await restart_paper_service()

    chunk_col = FakeCollection()
    store = VectorStore(
        paper_service=service,
        embedding_client=FakeEmbeddingClient(),
        chunk_collection=chunk_col,
        entity_collection=FakeCollection(),
        relation_collection=FakeCollection(),
    )

    # Physical late write: overdue worker deposited Run_A after wipe/remint.
    await store._index_chunks(
        [_chunk(paper_id, GHOST_MARKER, chunk_id="c_ghost")],
        run_id=RUN_A,
    )
    await store._index_chunks(
        [_chunk(paper_id, ACTIVE_MARKER, chunk_id="c_active")],
        run_id=RUN_B,
    )
    service.set_active_run_id(paper_id, RUN_B)
    assert service.get_active_run_id(paper_id) == RUN_B
    # Sanity: both generations physically coexist in Chroma.
    assert len(chunk_col.records) == 2
    assert any(GHOST_MARKER in str(rec["document"]) for rec in chunk_col.records.values())

    retriever = HybridRetriever(vector_store=store)
    rc = await retriever.retrieve(
        paper_id,
        "What is the active evidence payload?",
        _graph(paper_id),
        scale=QuestionScale.DETAIL,
        top_k=10,
    )

    chunk_texts = [chunk.text for chunk in rc.chunks]
    assert all(GHOST_MARKER not in text for text in chunk_texts), chunk_texts
    assert any(ACTIVE_MARKER in text for text in chunk_texts), chunk_texts
    # Direct store query path must agree with HybridRetriever soft isolation.
    direct = await store.query_chunks(ACTIVE_MARKER, paper_id=paper_id, top_k=10)
    assert all(GHOST_MARKER not in hit.text for hit in direct)
    assert any(ACTIVE_MARKER in hit.text for hit in direct)
