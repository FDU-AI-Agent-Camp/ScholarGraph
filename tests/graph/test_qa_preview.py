# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for qa_stream preview/MVP skeleton behaviour (Slice 1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from backend.graph.qa import _MVP_PREVIEW_PREFIX, _GraphQaEngine
from backend.graph.store import GraphStore
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service

from tests.helpers.persistence_testkit import register_test_paper


class _FakeChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChat:
    def __init__(self, text: str, chunk_size: int = 5) -> None:
        self._text = text
        self._chunk_size = chunk_size

    async def astream(self, _prompt: str) -> AsyncIterator[_FakeChunk]:
        for i in range(0, len(self._text), self._chunk_size):
            yield _FakeChunk(self._text[i : i + self._chunk_size])


def _fake_llm(text: str, chunk_size: int = 5) -> object:
    obj = type("FakeLlmClient", (), {})()
    obj.chat = _FakeChat(text, chunk_size)
    return obj


@pytest.fixture
def preview_graph() -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id="preview-qa-001",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
        edges=[],
    )


@pytest.fixture(autouse=True)
def _fresh_service() -> None:
    from backend.services.paper_service import get_paper_service

    get_paper_service.cache_clear()
    yield
    get_paper_service.cache_clear()


class TestQaStreamPreview:
    async def test_preview_paper_with_flag_allows_qa(
        self,
        preview_graph: UnifiedPaperGraph,
        persistence_env,
    ) -> None:
        paper_id = "preview-qa-001"
        await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
        service = get_paper_service()
        service.mark_preview_available(paper_id)
        service.save_preview_graph(paper_id, preview_graph)

        llm = _fake_llm("答案")
        engine = _GraphQaEngine(llm=llm, paper_service=service)

        events = [evt async for evt in engine.stream(paper_id, "核心论点是什么？")]
        messages = [e for e in events if e.event == "message"]
        errors = [e for e in events if e.event == "error"]

        assert len(errors) == 0
        assert len(messages) >= 1
        assert "".join(m.data["delta"] for m in messages) == "答案"

    async def test_prompt_includes_mvp_prefix_for_preview(
        self,
        preview_graph: UnifiedPaperGraph,
        persistence_env,
    ) -> None:
        paper_id = "preview-qa-002"
        await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
        service = get_paper_service()
        service.mark_preview_available(paper_id)
        service.save_preview_graph(paper_id, preview_graph)

        captured: list[str] = []

        class _RecordingLlm:
            class _Chat:
                def __init__(self, sink: list[str]) -> None:
                    self._sink = sink

                async def astream(self, prompt: str) -> AsyncIterator[_FakeChunk]:
                    self._sink.append(prompt)
                    yield _FakeChunk("ok")

            def __init__(self, sink: list[str]) -> None:
                self.chat = self._Chat(sink)

        llm = _RecordingLlm(captured)
        engine = _GraphQaEngine(llm=llm, paper_service=service)

        [evt async for evt in engine.stream(paper_id, "问题")]

        assert len(captured) == 1
        prompt = captured[0]
        assert _MVP_PREVIEW_PREFIX in prompt

    async def test_processing_paper_without_preview_is_rejected(self, persistence_env) -> None:
        paper_id = "preview-qa-003"
        await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
        service = get_paper_service()

        engine = _GraphQaEngine(paper_service=service)
        events = [evt async for evt in engine.stream(paper_id, "问题")]

        errors = [e for e in events if e.event == "error"]
        assert len(errors) == 1
        assert errors[0].data["code"] == "GRAPH_NOT_FOUND"
        assert events[-1].event == "done"

    async def test_missing_paper_returns_graph_not_found(self, tmp_path: Path) -> None:
        store = GraphStore(base_dir=tmp_path)
        engine = _GraphQaEngine(store=store)

        events = [evt async for evt in engine.stream("no-such-paper", "问题")]

        errors = [e for e in events if e.event == "error"]
        assert len(errors) == 1
        assert errors[0].data["code"] == "GRAPH_NOT_FOUND"
        assert events[-1].event == "done"

    async def test_ready_paper_does_not_inject_mvp_prefix(self, tmp_path: Path, persistence_env) -> None:
        paper_id = "preview-qa-ready-001"
        await register_test_paper(paper_id, status=PaperStatus.READY)
        service = get_paper_service()
        service.mark_preview_available(paper_id)
        full_graph = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.STEM,
            nodes=[GraphNode(id="n1", label="Method", type="Method")],
            edges=[],
        )
        store = GraphStore(base_dir=tmp_path)
        store.save(full_graph)

        captured: list[str] = []

        class _RecordingLlm:
            class _Chat:
                def __init__(self, sink: list[str]) -> None:
                    self._sink = sink

                async def astream(self, prompt: str) -> AsyncIterator[_FakeChunk]:
                    self._sink.append(prompt)
                    yield _FakeChunk("ok")

            def __init__(self, sink: list[str]) -> None:
                self.chat = self._Chat(sink)

        llm = _RecordingLlm(captured)
        engine = _GraphQaEngine(store=store, llm=llm, paper_service=service)

        [evt async for evt in engine.stream(paper_id, "问题")]

        assert len(captured) == 1
        assert _MVP_PREVIEW_PREFIX not in captured[0]
