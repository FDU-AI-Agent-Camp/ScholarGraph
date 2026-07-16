"""Phase E integration: head_refining stage, status warnings, head persistence (P7–P11)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import get_settings
from backend.graph.head_store import HeadStore
from backend.graph.workflow import run_paper_pipeline
from backend.main import app
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.head_refine_wait import HEAD_REFINE_TIMEOUT_WARNING
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient

from tests.conftest import mock_pipeline_node_services
from tests.helpers.status_contract import assert_snapshot_matches_contract

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_wait_head_refine_writes_head_refining_status(
    integration_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = integration_paper
    get_pipeline_status_service().start_processing(paper_id)

    async def _instant(_pid: str, _path: Path, fallback: str, **_: object) -> tuple[str, list[str]]:
        return "Title: Refined", ["grobid_unavailable"]

    with (
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch("backend.graph.nodes.wait_for_refined_classifier_input", side_effect=_instant),
    ):
        from backend.graph import nodes

        await nodes.wait_head_refine_node(
            {
                "paper_id": paper_id,
                "pdf_path": str(pdf_path),
                "classifier_input": "fallback",
            },
        )

    status = await get_paper_service().get_status(paper_id)
    assert status.stage == PipelineStage.HEAD_REFINING
    assert status.percent == 35
    assert status.head_refine_warnings == ["grobid_unavailable"]
    assert_snapshot_matches_contract(status)


@pytest.mark.asyncio
async def test_pipeline_timeout_warnings_visible_on_status_api(
    integration_paper: tuple[str, Path],
    api_client: AsyncClient,
) -> None:
    paper_id, pdf_path = integration_paper

    async def _timeout(_pid: str, _path: Path, fallback: str, **_: object) -> tuple[str, list[str]]:
        return fallback, [HEAD_REFINE_TIMEOUT_WARNING]

    with mock_pipeline_node_services(paper_id) as mocks:
        mocks["ingest"].ingest = AsyncMock(
            return_value={
                "paper_id": paper_id,
                "full_text": "body",
                "classifier_input": "SNIPPET-FALLBACK",
            },
        )
        with (
            patch("backend.graph.nodes.wait_for_refined_classifier_input", side_effect=_timeout),
            patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        ):
            await run_paper_pipeline(paper_id, pdf_path)

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert HEAD_REFINE_TIMEOUT_WARNING in data["head_refine_warnings"]


@pytest.mark.asyncio
async def test_head_refine_persists_and_survives_service_restart(
    integration_paper: tuple[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    api_client: AsyncClient,
) -> None:
    paper_id, _pdf_path = integration_paper
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()

    merged = IngestHead(
        title="Persisted Via API",
        abstract="Abstract text",
        sources={"title": "mineru", "abstract": "pymupdf"},
    )
    get_paper_service().apply_head_refine(
        paper_id,
        merged=merged,
        classifier_input="Title: Persisted Via API",
        warnings=["mineru_unavailable"],
    )
    assert HeadStore(base_dir=graph_dir).load(paper_id) is not None

    get_paper_service.cache_clear()
    detail_resp = await api_client.get(f"/api/v1/papers/{paper_id}")
    assert detail_resp.status_code == 200
    ingest_head = detail_resp.json()["data"].get("ingest_head")
    assert ingest_head is not None
    assert ingest_head["title"] == "Persisted Via API"
    assert ingest_head["sources"]["title"] == "mineru"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pipeline_emits_head_refining_stage_in_status_writes(
    integration_paper: tuple[str, Path],
) -> None:
    """Full pipeline (mocked agents) should pass through head_refining before classify."""
    from backend.schemas.paper import PaperStatusData
    from backend.services.pipeline_status_service import PipelineStatusService

    paper_id, pdf_path = integration_paper
    writes: list[PaperStatusData] = []
    original_apply = PipelineStatusService._apply

    def recording_apply(
        self: PipelineStatusService,
        pid: str,
        *,
        status,
        stage,
        percent,
        message,
        error_code=None,
        failed_during=None,
    ) -> PaperStatusData:
        snapshot = original_apply(
            self,
            pid,
            status=status,
            stage=stage,
            percent=percent,
            message=message,
            error_code=error_code,
            failed_during=failed_during,
        )
        writes.append(snapshot)
        return snapshot

    with mock_pipeline_node_services(paper_id):
        with patch.object(PipelineStatusService, "_apply", recording_apply):
            await run_paper_pipeline(paper_id, pdf_path)

    stages = [snapshot.stage for snapshot in writes if snapshot.status == PaperStatus.PROCESSING]
    assert PipelineStage.HEAD_REFINING in stages
