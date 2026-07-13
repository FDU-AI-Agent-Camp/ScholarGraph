"""Integration tests: upload → ready → restart → list still present."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from backend.graph.qa import _GraphQaEngine
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.pipeline_completion_service import PipelineCompletionService
from httpx import AsyncClient

from tests.graph.test_qa import _fake_llm
from tests.helpers.persistence_testkit import (
    mock_graph_persistence,
    restart_paper_service,
    simulate_service_crash,
)
from tests.helpers.qa_stream_mock import qa_stream_from_engine

VALID_PDF = b"%PDF-1.4\n% persistence restart test"


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upload_ready_survives_service_restart(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_dir = persistence_env["upload_dir"]
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)

    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("restart.pdf", VALID_PDF, "application/pdf")},
    )
    assert create.status_code == 201
    paper_id = create.json()["data"]["paper_id"]

    classification = ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="integration")
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="Claim", type="Thesis")],
        edges=[
            GraphEdge(id="e1", source="n1", target="n1", label="REF", type="REF"),
        ],
    )
    persistence = mock_graph_persistence(paper_id, graph_dir=persistence_env["graph_dir"])
    completion = PipelineCompletionService(graph_persistence=persistence)
    with patch(
        "backend.services.rag_index_service.RagIndexService.index_paper_for_rag_async",
        new_callable=AsyncMock,
    ):
        completion.finalize(
            paper_id,
            graph_data=graph.model_dump(mode="json"),
            classification_data=classification.model_dump(mode="json"),
            full_text="restart integration full text body",
        )

    service = await restart_paper_service()
    items, total = await service.list_papers()
    assert total >= 1
    assert any(item.paper_id == paper_id for item in items)

    detail = await service.get_paper(paper_id)
    assert detail.status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS)
    assert (upload_dir / f"{paper_id}.pdf").is_file()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_status_persists_across_restart(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("status-restart", "Status", str(persistence_env["upload_dir"] / "x.pdf"))
    from backend.repositories.pipeline_repository import PipelineRepository

    pipeline_repo = PipelineRepository()
    now = datetime.now(UTC)
    await pipeline_repo.save_status(
        "status-restart",
        PaperStatusData(
            paper_id="status-restart",
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="classifying",
            updated_at=now,
        ),
    )

    service = await restart_paper_service()
    status = await service.get_status("status-restart")
    assert status.stage == PipelineStage.CLASSIFYING
    assert status.percent == 50


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mid_pipeline_ephemeral_state_survives_crash_recovery(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D6 crash-recovery: preview graph + active RAG run_id survive service restart."""
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)

    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("crash-mid.pdf", VALID_PDF, "application/pdf")},
    )
    assert create.status_code == 201
    paper_id = create.json()["data"]["paper_id"]
    active_run_id = f"run-crash-{paper_id[:8]}"

    preview = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n_preview", label="崩溃前预览论点", type="Thesis"),
            GraphNode(id="n_sub", label="分论点", type="SubArgument"),
        ],
        edges=[
            GraphEdge(
                id="e_preview",
                source="n_sub",
                target="n_preview",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
        ],
    )

    from backend.services.paper_service import get_paper_service

    service = get_paper_service()
    pipeline_repo = PipelineRepository()
    await pipeline_repo.save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PROCESSING,
            percent=45,
            stage=PipelineStage.EXTRACTING,
            message="抽取中（模拟崩溃前中途态）",
            updated_at=datetime.now(UTC),
        ),
    )
    service.save_preview_graph(paper_id, preview)
    service.set_active_run_id(paper_id, active_run_id)
    service.mark_preview_available(paper_id)

    persisted_preview = await pipeline_repo.get_preview_graph(paper_id)
    assert persisted_preview is not None
    assert persisted_preview.nodes[0].id == "n_preview"
    assert await pipeline_repo.get_active_rag_run_id(paper_id) == active_run_id

    simulate_service_crash()

    restarted = await restart_paper_service()
    assert restarted.get_active_run_id(paper_id) == active_run_id

    loaded_preview = restarted.get_preview_graph(paper_id)
    assert loaded_preview is not None
    assert loaded_preview.paper_id == paper_id
    assert any(node.id == "n_preview" for node in loaded_preview.nodes)

    graph_response = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph_response.status_code == 200
    graph_body = graph_response.json()
    assert graph_body["data"]["paper_id"] == paper_id
    assert any(node["id"] == "n_preview" for node in graph_body["data"]["nodes"])

    engine = _GraphQaEngine(paper_service=restarted, llm=_fake_llm("崩溃恢复后仍可预览问答"))
    monkeypatch.setattr("backend.graph.qa.qa_stream", qa_stream_from_engine(engine))

    qa_response = await api_client.post(
        f"/api/v1/papers/{paper_id}/qa/stream",
        json={"question": "核心论点是什么？"},
    )
    assert qa_response.status_code == 200
    events = _parse_sse(qa_response.text)
    event_names = [name for name, _ in events]
    assert "message" in event_names
    assert event_names[-1] == "done"
    answer_text = "".join(payload["delta"] for name, payload in events if name == "message")
    assert "崩溃恢复后仍可预览问答" in answer_text
