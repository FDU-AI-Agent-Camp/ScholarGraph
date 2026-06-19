"""HTTP integration tests for preview graph / preview QA (Slice 1)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from backend.graph.qa import QaEvent, _GraphQaEngine
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.graph.test_qa import _fake_llm


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((event_name, payload))
    return events


def _get_service():
    from backend.services.paper_service import get_paper_service

    return get_paper_service()


def _make_preview_paper(paper_id: str) -> PaperDetail:
    now = datetime.now(UTC)
    return PaperDetail(
        paper_id=paper_id,
        title="preview api test",
        status=PaperStatus.PROCESSING,
        preview_available=True,
        created_at=now,
        updated_at=now,
    )


def _make_status(paper_id: str) -> PaperStatusData:
    return PaperStatusData(
        paper_id=paper_id,
        status=PaperStatus.PROCESSING,
        percent=20,
        stage=PipelineStage.EXTRACTING,
        message="抽取中",
        updated_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def _fresh_service() -> None:
    from backend.services.paper_service import get_paper_service

    get_paper_service.cache_clear()
    yield
    get_paper_service.cache_clear()


class TestPreviewGraphApi:
    async def test_get_graph_returns_preview_when_preview_available(self, api_client: AsyncClient) -> None:
        paper_id = "preview-api-001"
        service = _get_service()
        service._papers[paper_id] = _make_preview_paper(paper_id)
        service._status[paper_id] = _make_status(paper_id)
        preview = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
            edges=[],
        )
        service.save_preview_graph(paper_id, preview)
        service.mark_preview_available(paper_id)

        response = await api_client.get(f"/api/v1/papers/{paper_id}/graph")

        assert response.status_code == 200
        body = response.json()
        assert_success_envelope(body)
        assert body["data"]["paper_id"] == paper_id
        assert any(node["id"] == "n1" for node in body["data"]["nodes"])

    async def test_get_graph_returns_409_when_processing_without_preview(self, api_client: AsyncClient) -> None:
        paper_id = "preview-api-002"
        service = _get_service()
        service._papers[paper_id] = PaperDetail(
            paper_id=paper_id,
            title="no preview",
            status=PaperStatus.PROCESSING,
            preview_available=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        service._status[paper_id] = _make_status(paper_id)

        response = await api_client.get(f"/api/v1/papers/{paper_id}/graph")

        assert response.status_code == 409
        assert_error_envelope(response.json(), code="GRAPH_NOT_READY")

    async def test_get_status_includes_preview_available(self, api_client: AsyncClient) -> None:
        paper_id = "preview-api-003"
        service = _get_service()
        service._papers[paper_id] = _make_preview_paper(paper_id)
        service._status[paper_id] = _make_status(paper_id)
        service.mark_preview_available(paper_id)

        response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

        assert response.status_code == 200
        body = response.json()
        assert_success_envelope(body)
        assert body["data"]["preview_available"] is True

    async def test_get_paper_detail_includes_preview_available(self, api_client: AsyncClient) -> None:
        paper_id = "preview-api-004"
        service = _get_service()
        service._papers[paper_id] = _make_preview_paper(paper_id)
        service.mark_preview_available(paper_id)

        response = await api_client.get(f"/api/v1/papers/{paper_id}")

        assert response.status_code == 200
        body = response.json()
        assert_success_envelope(body)
        assert body["data"]["preview_available"] is True


class TestPreviewQaStreamApi:
    async def test_qa_stream_on_preview_paper_returns_answer(
        self,
        api_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "preview-api-qa-001"
        service = _get_service()
        service._papers[paper_id] = _make_preview_paper(paper_id)
        service._status[paper_id] = _make_status(paper_id)
        preview = UnifiedPaperGraph(
            paper_id=paper_id,
            paradigm=Paradigm.HSS,
            nodes=[GraphNode(id="n1", label="Thesis", type="Thesis")],
            edges=[],
        )
        service.save_preview_graph(paper_id, preview)
        service.mark_preview_available(paper_id)

        engine = _GraphQaEngine(paper_service=service, llm=_fake_llm("宏观答案"))

        async def _fake_qa_stream(_paper_id: str, question: str) -> AsyncIterator[QaEvent]:
            async for evt in engine.stream(_paper_id, question):
                yield evt

        monkeypatch.setattr("backend.graph.qa.qa_stream", _fake_qa_stream)

        response = await api_client.post(
            f"/api/v1/papers/{paper_id}/qa/stream",
            json={"question": "核心问题是什么？"},
        )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        event_names = [name for name, _ in events]
        assert "message" in event_names
        assert event_names[-1] == "done"
        full_text = "".join(payload["delta"] for name, payload in events if name == "message")
        assert "宏观答案" in full_text

    async def test_qa_stream_on_processing_paper_without_preview_emits_graph_not_found(
        self,
        api_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        paper_id = "preview-api-qa-002"
        service = _get_service()
        service._papers[paper_id] = PaperDetail(
            paper_id=paper_id,
            title="no preview",
            status=PaperStatus.PROCESSING,
            preview_available=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        service._status[paper_id] = _make_status(paper_id)

        engine = _GraphQaEngine(paper_service=service)

        async def _fake_qa_stream(_paper_id: str, question: str) -> AsyncIterator[QaEvent]:
            async for evt in engine.stream(_paper_id, question):
                yield evt

        monkeypatch.setattr("backend.graph.qa.qa_stream", _fake_qa_stream)

        response = await api_client.post(
            f"/api/v1/papers/{paper_id}/qa/stream",
            json={"question": "test"},
        )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[0][0] == "error"
        assert events[0][1]["code"] == "GRAPH_NOT_FOUND"
        assert events[-1][0] == "done"
