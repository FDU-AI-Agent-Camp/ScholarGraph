# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for LLM mock mode (LLM_MODE=mock)."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa import qa_stream
from backend.graph.store import GraphStore
from backend.llm.client import get_llm_client, reset_llm_client_cache
from backend.llm.mock_chat import MOCK_DISCLAIMER
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm


@pytest.fixture(autouse=True)
def _llm_mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.delenv("SCHOLARGRAPH_API_KEY", raising=False)
    get_settings.cache_clear()
    reset_llm_client_cache()


def test_llm_client_mock_mode_without_api_key() -> None:
    client = get_llm_client()
    assert client.is_mock is True
    assert client.chat.model_name == "DeepSeek-V3-64K"


@pytest.mark.asyncio
async def test_qa_stream_uses_mock_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    store = GraphStore(base_dir=tmp_path)
    store.save(
        UnifiedPaperGraph(
            paper_id="hss-001",
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="核心论点", type="Thesis", data={})],
            edges=[],
        ),
    )

    events: list[tuple[str, dict]] = []
    async for evt in qa_stream("hss-001", "核心论点是什么？"):
        events.append((evt.event, evt.data))

    messages = "".join(payload["delta"] for name, payload in events if name == "message")
    assert MOCK_DISCLAIMER in messages
    citations = [payload for name, payload in events if name == "citation"]
    assert citations
    assert citations[0]["node_id"] == "n1"
    assert events[-1][0] == "done"
