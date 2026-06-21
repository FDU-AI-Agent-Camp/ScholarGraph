"""HTTP interface tests for Slice 2 background full extraction.

These tests hit the real FastAPI endpoints and verify the observable contract:
- long papers schedule background extraction and return pending immediately
- status polling shows the extracting stage before ready
- GET /papers/{id}/graph returns 409 while background extraction runs
- the paper eventually reaches ready and the graph endpoint succeeds
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.api.test_papers_upload import VALID_PDF

pytestmark = pytest.mark.asyncio


async def _poll_status_until_terminal(
    api_client: AsyncClient,
    paper_id: str,
    *,
    max_attempts: int = 120,
    interval_s: float = 0.05,
) -> dict:
    last: dict = {}
    for _ in range(max_attempts):
        await asyncio.sleep(interval_s)
        response = await api_client.get(f"/api/v1/papers/{paper_id}/status")
        assert response.status_code == 200
        last = response.json()["data"]
        if last["status"] in ("ready", "failed"):
            return last
    return last


async def test_long_paper_upload_reaches_ready_via_background_extraction(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    """Long papers take the background extract path and eventually become ready."""
    upload_dir, graph_dir = mock_upload_pipeline_env

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": "will-be-replaced",
            "full_text": "x" * 50_000,
            "classifier_input": "classification input",
        },
    )

    from backend.services.extract_worker import _extract_chunked_two_phase as _original_extract

    async def slow_full_extraction(*args, **kwargs):
        await asyncio.sleep(0.1)
        return await _original_extract(*args, **kwargs)

    with (
        patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
        ),
        patch("backend.services.agent_service.should_run_background_extraction", return_value=True),
        patch(
            "backend.services.extract_worker._extract_chunked_two_phase",
            new=slow_full_extraction,
        ),
    ):
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("long-paper.pdf", VALID_PDF, "application/pdf")},
        )
        assert create.status_code == 201
        body = create.json()
        assert_success_envelope(body)
        paper_id = body["data"]["paper_id"]

        saw_extracting = False
        final: dict = {}
        for _ in range(120):
            await asyncio.sleep(0.05)
            status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
            final = status_resp.json()["data"]
            if final.get("stage") == "extracting":
                saw_extracting = True
            if final["status"] in ("ready", "failed"):
                break

        assert saw_extracting, "background extraction should surface the extracting stage"
        assert final["status"] == "ready"
        assert final["stage"] == "ready"
        assert final["percent"] == 100

    detail = await api_client.get(f"/api/v1/papers/{paper_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "ready"

    graph = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph.status_code == 200
    graph_body = graph.json()
    assert_success_envelope(graph_body)
    assert graph_body["data"]["paper_id"] == paper_id
    assert (graph_dir / f"{paper_id}.json").is_file()


async def test_graph_returns_409_while_background_extraction_runs(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    """GET /graph before background extraction finishes must return 409."""
    _upload_dir, _graph_dir = mock_upload_pipeline_env

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": "will-be-replaced",
            "full_text": "x" * 50_000,
            "classifier_input": "classification input",
        },
    )

    from backend.services.extract_worker import _extract_chunked_two_phase as _original_extract

    async def slow_full_extraction(*args, **kwargs):
        await asyncio.sleep(0.3)
        return await _original_extract(*args, **kwargs)

    with (
        patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
        ),
        patch("backend.services.agent_service.should_run_background_extraction", return_value=True),
        patch(
            "backend.services.extract_worker._extract_chunked_two_phase",
            new=slow_full_extraction,
        ),
    ):
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("slow-bg.pdf", VALID_PDF, "application/pdf")},
        )
        paper_id = create.json()["data"]["paper_id"]

        saw_409 = False
        for _ in range(40):
            await asyncio.sleep(0.05)
            graph_resp = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
            if graph_resp.status_code == 409:
                saw_409 = True
                assert_error_envelope(graph_resp.json(), code="GRAPH_NOT_READY")
                break
            status = (await api_client.get(f"/api/v1/papers/{paper_id}/status")).json()["data"]
            if status["status"] in ("ready", "failed"):
                break

        assert saw_409, "graph endpoint should return 409 while background extraction runs"

        final = await _poll_status_until_terminal(api_client, paper_id)
        assert final["status"] == "ready"


async def test_background_extraction_failed_marks_paper_failed(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    """If the background worker fails, status polling must eventually report failed."""
    _upload_dir, _graph_dir = mock_upload_pipeline_env

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": "will-be-replaced",
            "full_text": "x" * 50_000,
            "classifier_input": "classification input",
        },
    )

    async def failing_full_extraction(*_args, **_kwargs):
        raise RuntimeError("background extraction failed")

    with (
        patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
        patch("backend.graph.nodes.ensure_head_refine_scheduled"),
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new=AsyncMock(side_effect=lambda _pid, _path, fallback, **_: (fallback, [])),
        ),
        patch("backend.services.agent_service.should_run_background_extraction", return_value=True),
        patch(
            "backend.services.extract_worker._extract_chunked_two_phase",
            new=failing_full_extraction,
        ),
    ):
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("failing-bg.pdf", VALID_PDF, "application/pdf")},
        )
        paper_id = create.json()["data"]["paper_id"]

        final = await _poll_status_until_terminal(api_client, paper_id)
        assert final["status"] == "failed"
        assert final["stage"] == "failed"
        assert final.get("error_code")
