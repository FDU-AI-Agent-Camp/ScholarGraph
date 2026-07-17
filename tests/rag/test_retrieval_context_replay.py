# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""B7 — offline RetrievalContext JSON replay (zero vector/graph re-fetch)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.query import GraphQuery
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import RetrievalContext
from backend.rag.retrieval_context_io import (
    deserialize_retrieval_context,
    load_replay_bundle,
    serialize_retrieval_context,
    sha256_prompt,
)

from tests.fixtures.retrieval_context_replay import HSS_DETAIL_REPLAY_PATH, load_hss_detail_replay_bundle
from tests.graph.test_qa import _FakeChunk


class _CapturingFakeChat:
    """Records the full prompt passed to the fake LLM."""

    def __init__(self) -> None:
        self.prompt = ""

    async def astream(self, prompt: str) -> AsyncIterator[_FakeChunk]:
        self.prompt = prompt
        yield _FakeChunk("离线回放[CITE:n1]。")


def _capturing_llm() -> tuple[object, _CapturingFakeChat]:
    chat = _CapturingFakeChat()
    client = type("ReplayCapturingLlmClient", (), {})()
    client.chat = chat
    return client, chat


def _forbidden_graph_query(*_args: object, **_kwargs: object) -> dict:
    raise AssertionError("GraphQuery must not run during offline RC replay")


def _forbidden_hybrid_retrieve(*_args: object, **_kwargs: object) -> RetrievalContext:
    raise AssertionError("HybridRetriever must not run during offline RC replay")


@pytest.fixture
def replay_graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
    """Minimal on-disk graph for paper metadata only — prompt body comes from RC JSON."""
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()

    from tests.rag.test_context_source_unification import _seed_graph_store

    return _seed_graph_store(graph_dir)


def test_retrieval_context_json_round_trip_matches_bundle() -> None:
    """JSON serialize → deserialize must preserve the frozen RC contract."""
    bundle = load_hss_detail_replay_bundle()
    payload = serialize_retrieval_context(bundle.retrieval_context)
    restored = deserialize_retrieval_context(payload)

    assert restored.model_dump(mode="json") == bundle.retrieval_context.model_dump(mode="json")
    assert restored.scale == bundle.retrieval_context.scale
    assert len(restored.chunks) == len(bundle.retrieval_context.chunks)


def test_replay_bundle_file_loads_with_prompt_hash() -> None:
    bundle = load_replay_bundle(HSS_DETAIL_REPLAY_PATH)
    assert bundle.schema_version == 1
    assert bundle.paper_id == "hss-001"
    assert bundle.retrieval_context.nodes
    assert bundle.retrieval_context.edges
    assert bundle.retrieval_context.chunks
    assert sha256_prompt(bundle.expected_prompt) == bundle.expected_prompt_sha256


@pytest.mark.asyncio
async def test_offline_replay_renders_identical_prompt_without_database_io(
    replay_graph_env: GraphStore,
) -> None:
    """Replay JSON → qa_stream with GraphQuery/HybridRetriever blocked → golden prompt."""
    bundle = load_hss_detail_replay_bundle()
    llm, chat = _capturing_llm()

    with (
        patch.object(GraphQuery, "subgraph_for_question", side_effect=_forbidden_graph_query),
        patch.object(HybridRetriever, "retrieve", side_effect=_forbidden_hybrid_retrieve),
    ):
        events = [
            evt
            async for evt in qa_stream(
                bundle.paper_id,
                bundle.question,
                retrieval_context=bundle.retrieval_context,
                llm=llm,
            )
        ]

    assert not any(evt.event == "error" for evt in events)
    assert events[-1].event == "done"
    assert chat.prompt == bundle.expected_prompt
    assert sha256_prompt(chat.prompt) == bundle.expected_prompt_sha256
