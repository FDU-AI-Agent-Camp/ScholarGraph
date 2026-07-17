# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Contract Drift Test: ``active_run_id`` SSOT survives restart for RAG ``index_run_id`` filter."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from backend.rag.vector_store import VectorStore
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service

from tests.helpers.persistence_testkit import (
    register_test_paper,
    restart_paper_service,
    simulate_service_crash,
)
from tests.helpers.rag_contract_testkit import IndexRunMetadataStore
from tests.integration.test_rag_vector_store_run_id import FakeEmbeddingClient, _chunk


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_index_run_id_contract_survives_hard_restart_mock_consumer(
    persistence_env,
) -> None:
    """Downstream shim: write with SSOT run_id → crash → re-read → filter must hit 100%."""
    paper_id = "rag-contract-mock"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)

    downstream_store = IndexRunMetadataStore()
    service = get_paper_service()

    # Pipeline commit point: activate a new RAG index run (mirrors VectorStore.replace tail).
    committed_run_id = "run-contract-pre-crash"
    service.set_active_run_id(paper_id, committed_run_id)
    ssot_run_id = service.get_active_run_id(paper_id)
    assert ssot_run_id == committed_run_id

    # 组员 A branch: index with metadata.index_run_id sourced from PaperService SSOT.
    downstream_store.upsert(
        paper_id=paper_id,
        index_run_id=ssot_run_id,
        record_id="chunk-0",
        payload="contract drift payload — 组员 A 可检索",
    )

    simulate_service_crash()
    restarted = await restart_paper_service()

    recovered_run_id = restarted.get_active_run_id(paper_id)
    assert recovered_run_id == committed_run_id

    hits = downstream_store.filter_by_index_run_id(
        paper_id=paper_id,
        index_run_id=recovered_run_id,
    )
    assert len(hits) == 1
    assert hits[0].record_id == "chunk-0"
    assert hits[0].index_run_id == committed_run_id
    assert hits[0].payload == "contract drift payload — 组员 A 可检索"

    stale_hits = downstream_store.filter_by_index_run_id(
        paper_id=paper_id,
        index_run_id="run-stale-never-committed",
    )
    assert stale_hits == []


@pytest.fixture
def temp_chroma_path() -> Any:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        yield Path(tmp_dir)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_store_index_run_id_filter_survives_hard_restart(
    persistence_env,
    temp_chroma_path: Path,
) -> None:
    """Real Chroma path: indexed chunks remain visible after SSOT run_id recovery."""
    paper_id = "rag-contract-chroma"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)

    service = get_paper_service()
    store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=service,
    )

    chunk_text = "restart-safe RAG chunk for index_run_id contract"
    await store.replace_paper_index(
        paper_id,
        chunks=[_chunk(paper_id, 0, chunk_text)],
        entities=[],
        relations=[],
    )
    pre_crash_run_id = service.get_active_run_id(paper_id)
    assert pre_crash_run_id

    simulate_service_crash()
    restarted = await restart_paper_service()
    post_restart_run_id = restarted.get_active_run_id(paper_id)
    assert post_restart_run_id == pre_crash_run_id

    restarted_store = VectorStore(
        embedding_client=FakeEmbeddingClient(),
        chroma_path=str(temp_chroma_path),
        paper_service=restarted,
    )
    query_hits = await restarted_store.query_chunks("restart-safe", paper_id=paper_id, top_k=5)
    assert len(query_hits) == 1
    assert query_hits[0].text == chunk_text

    collection = restarted_store._chunk_collection
    filtered = collection.get(
        where={"index_run_id": post_restart_run_id},
        include=["metadatas", "documents"],
    )
    assert filtered["ids"]
    assert len(filtered["ids"]) == 1
    metadata = filtered["metadatas"][0]
    assert metadata is not None
    assert metadata.get("index_run_id") == post_restart_run_id
    assert metadata.get("paper_id") == paper_id
    assert filtered["documents"][0] == chunk_text
