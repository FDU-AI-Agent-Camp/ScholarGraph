"""HTTP API: Phase E observability — head_refining stage, warnings, ingest_head (P7–P11)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.graph.state import STAGE_PERCENT
from backend.main import app
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperDetail, PaperStatus, PipelineStage
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient
from tests.api.conftest import assert_success_envelope
from tests.helpers.status_contract import assert_status_contract

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _register_paper(paper_id: str) -> None:
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="observability api test",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_status_api_head_refining_stage_and_percent(api_client: AsyncClient) -> None:
    paper_id = "api-head-refining-001"
    _register_paper(paper_id)
    get_pipeline_status_service().advance_stage(
        paper_id,
        PipelineStage.HEAD_REFINING,
        message="正在精炼文档头部…",
    )

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["stage"] == "head_refining"
    assert data["percent"] == STAGE_PERCENT[PipelineStage.HEAD_REFINING]
    assert_status_contract(
        status=PaperStatus(data["status"]),
        stage=PipelineStage.HEAD_REFINING,
        percent=data["percent"],
    )


@pytest.mark.asyncio
async def test_status_api_returns_head_refine_warnings_list(api_client: AsyncClient) -> None:
    paper_id = "hss-002"
    get_paper_service().record_head_refine_warnings(
        paper_id,
        ["mineru_unavailable", "head_refine_timeout"],
    )

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    warnings = response.json()["data"]["head_refine_warnings"]
    assert warnings == ["mineru_unavailable", "head_refine_timeout"]


@pytest.mark.asyncio
async def test_paper_detail_api_returns_ingest_head_with_sources(
    api_client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.config import get_settings
    from backend.graph.head_store import HeadStore

    paper_id = "api-ingest-head-001"
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()

    _register_paper(paper_id)
    merged = IngestHead(
        title="API Head",
        abstract="From GROBID",
        sources={"title": "grobid", "abstract": "grobid"},
    )
    get_paper_service().apply_head_refine(
        paper_id,
        merged=merged,
        classifier_input="Title: API Head",
        warnings=[],
    )
    assert HeadStore(base_dir=graph_dir).load(paper_id) is not None

    response = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    ingest_head = body["data"]["ingest_head"]
    assert ingest_head["title"] == "API Head"
    assert ingest_head["sources"]["title"] == "grobid"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_ready_fixture_status_includes_empty_head_refine_warnings(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers/hss-001/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "head_refine_warnings" in data
    assert data["head_refine_warnings"] == []
