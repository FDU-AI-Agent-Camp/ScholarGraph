"""Boundary / red tests: extract_worker resilience and MVP skeleton survival.

These tests deliberately break the background full-extraction pipeline and
verify that:

1. The worker catches exceptions and marks the pipeline as failed.
2. The Slice-1 MVP preview graph survives the crash.
3. QA still works using the preview skeleton while the full graph failed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from backend.config import Settings
from backend.graph.qa import _GraphQaEngine
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import ServiceError
from backend.services.extract_worker import reset_extract_worker, schedule_full_extraction
from backend.services.paper_service import get_paper_service

pytestmark = [pytest.mark.asyncio, pytest.mark.red]


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


def _fake_llm(text: str) -> object:
    obj = type("FakeLlmClient", (), {})()
    obj.chat = _FakeChat(text)
    return obj


def _make_preview_graph(paper_id: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="核心论点", type="Thesis"),
            GraphNode(id="n2", label="情感共鸣", type="Claim"),
        ],
        edges=[GraphEdge(id="e1", source="n1", target="n2", label="supports", type="SUPPORTS")],
    )


def _setup_paper_with_preview(paper_id: str) -> None:
    """Create a paper in PROCESSING state with an available MVP preview graph."""
    service = get_paper_service()
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="red-test-paper",
        status=PaperStatus.PROCESSING,
        preview_available=True,
        created_at=now,
        updated_at=now,
    )
    service._status[paper_id] = service.set_status_snapshot(
        paper_id,
        status=PaperStatus.PROCESSING,
        stage=PipelineStage.EXTRACTING,
        percent=80,
        message="全量抽取已在后台启动，可先预览 MVP 骨架",
    )
    service.mark_preview_available(paper_id)
    service.save_preview_graph(paper_id, _make_preview_graph(paper_id))


@pytest.fixture(autouse=True)
def _fresh_service() -> None:
    get_paper_service.cache_clear()
    reset_extract_worker()
    yield
    get_paper_service.cache_clear()
    reset_extract_worker()


async def test_worker_catches_generic_exception_and_marks_failed() -> None:
    paper_id = "red-worker-generic-fail"
    _setup_paper_with_preview(paper_id)

    async def boom(*args, **kwargs) -> None:
        raise RuntimeError("network down")

    settings = Settings(_env_file=None, llm_mode="mock")
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")

    with patch("backend.services.extract_worker._extract_chunked_two_phase", new=boom):
        task = schedule_full_extraction(
            paper_id,
            full_text="some long text that triggers background extraction",
            paradigm=Paradigm.HSS,
            classification=classification,
            settings=settings,
        )
        await task

    service = get_paper_service()
    snapshot = await service.get_status(paper_id)
    assert snapshot.status == PaperStatus.FAILED
    assert snapshot.stage == PipelineStage.FAILED
    assert snapshot.percent == 0
    assert snapshot.error_code == "PIPELINE_FAILED"
    assert snapshot.failed_during == PipelineStage.EXTRACTING


async def test_worker_catches_service_error_and_preserves_code() -> None:
    paper_id = "red-worker-service-error"
    _setup_paper_with_preview(paper_id)

    async def service_boom(*args, **kwargs) -> None:
        raise ServiceError("INGEST_FAILED", "无法解析")

    settings = Settings(_env_file=None, llm_mode="mock")
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")

    with patch("backend.services.extract_worker._extract_chunked_two_phase", new=service_boom):
        task = schedule_full_extraction(
            paper_id,
            full_text="some long text",
            paradigm=Paradigm.HSS,
            classification=classification,
            settings=settings,
        )
        await task

    snapshot = await get_paper_service().get_status(paper_id)
    assert snapshot.status == PaperStatus.FAILED
    assert snapshot.error_code == "INGEST_FAILED"
    assert snapshot.failed_during == PipelineStage.EXTRACTING


async def test_preview_graph_survives_full_extraction_failure() -> None:
    paper_id = "red-preview-survives"
    _setup_paper_with_preview(paper_id)
    expected_graph = _make_preview_graph(paper_id)

    async def boom(*args, **kwargs) -> None:
        raise RuntimeError("network down")

    settings = Settings(_env_file=None, llm_mode="mock")
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")

    with patch("backend.services.extract_worker._extract_chunked_two_phase", new=boom):
        task = schedule_full_extraction(
            paper_id,
            full_text="some long text",
            paradigm=Paradigm.HSS,
            classification=classification,
            settings=settings,
        )
        await task

    service = get_paper_service()
    assert service.is_preview_available(paper_id)
    preview = service.get_preview_graph(paper_id)
    assert preview is not None
    assert preview.paper_id == paper_id
    assert {n.id for n in preview.nodes} == {n.id for n in expected_graph.nodes}


async def test_qa_still_works_using_preview_after_full_failure() -> None:
    paper_id = "red-qa-after-failure"
    _setup_paper_with_preview(paper_id)

    async def boom(*args, **kwargs) -> None:
        raise RuntimeError("network down")

    settings = Settings(_env_file=None, llm_mode="mock")
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")

    with patch("backend.services.extract_worker._extract_chunked_two_phase", new=boom):
        task = schedule_full_extraction(
            paper_id,
            full_text="some long text",
            paradigm=Paradigm.HSS,
            classification=classification,
            settings=settings,
        )
        await task

    service = get_paper_service()
    assert (await service.get_status(paper_id)).status == PaperStatus.FAILED

    llm = _fake_llm("基于MVP骨架的回答")
    engine = _GraphQaEngine(llm=llm, paper_service=service)
    events = [evt async for evt in engine.stream(paper_id, "核心论点是什么？")]

    errors = [e for e in events if e.event == "error"]
    messages = [e for e in events if e.event == "message"]

    assert len(errors) == 0
    assert len(messages) >= 1
    assert "".join(m.data["delta"] for m in messages) == "基于MVP骨架的回答"


async def test_graph_endpoint_returns_preview_when_full_extraction_failed() -> None:
    paper_id = "red-graph-preview-fallback"
    _setup_paper_with_preview(paper_id)

    async def boom(*args, **kwargs) -> None:
        raise RuntimeError("network down")

    settings = Settings(_env_file=None, llm_mode="mock")
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")

    with patch("backend.services.extract_worker._extract_chunked_two_phase", new=boom):
        task = schedule_full_extraction(
            paper_id,
            full_text="some long text",
            paradigm=Paradigm.HSS,
            classification=classification,
            settings=settings,
        )
        await task

    service = get_paper_service()
    graph = await service.get_graph(paper_id)
    assert graph.paper_id == paper_id
    assert {n.id for n in graph.nodes} == {"n1", "n2"}


async def test_graph_endpoint_fails_when_no_preview_and_full_extraction_failed() -> None:
    paper_id = "red-graph-no-preview-fail"
    service = get_paper_service()
    now = datetime.now(UTC)
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="red-test-no-preview",
        status=PaperStatus.PROCESSING,
        preview_available=False,
        created_at=now,
        updated_at=now,
    )
    service.set_status_snapshot(
        paper_id,
        status=PaperStatus.PROCESSING,
        stage=PipelineStage.EXTRACTING,
        percent=80,
        message="后台抽取中",
    )

    async def boom(*args, **kwargs) -> None:
        raise RuntimeError("network down")

    settings = Settings(_env_file=None, llm_mode="mock")
    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="mock")

    with patch("backend.services.extract_worker._extract_chunked_two_phase", new=boom):
        task = schedule_full_extraction(
            paper_id,
            full_text="some long text",
            paradigm=Paradigm.HSS,
            classification=classification,
            settings=settings,
        )
        await task

    from backend.api.exceptions import ApiError

    with pytest.raises(ApiError) as exc_info:
        await service.get_graph(paper_id)
    assert exc_info.value.code == "GRAPH_NOT_READY"
