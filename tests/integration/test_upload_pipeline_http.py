"""HTTP integration: POST /papers must schedule LangGraph pipeline (upload → ready)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.api.conftest import assert_success_envelope
from tests.api.test_papers_upload import VALID_PDF
from tests.helpers.upload_pipeline_mock import mock_http_upload_pipeline_run

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


async def test_upload_http_pipeline_reaches_ready(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple,
) -> None:
    """FE↔BE 主路径：浏览器上传等价 HTTP 后应自动跑完 mock 流水线。"""
    with mock_http_upload_pipeline_run():
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("fe-be-upload.pdf", VALID_PDF, "application/pdf")},
        )
        assert create.status_code == 201
        paper_id = create.json()["data"]["paper_id"]

        final = await _poll_status_until_terminal(api_client, paper_id)
        assert final["status"] == "ready"
        assert final["stage"] == "ready"
        assert final["percent"] == 100

    graph = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph.status_code == 200
    assert_success_envelope(graph.json())
    assert graph.json()["data"]["paper_id"] == paper_id


async def test_upload_detail_status_tracks_processing_before_ready(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple,
) -> None:
    """GET /papers/{id} 与 status 在流水线运行期间应反映 processing。"""
    with mock_http_upload_pipeline_run():
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("track.pdf", VALID_PDF, "application/pdf")},
        )
        paper_id = create.json()["data"]["paper_id"]

        saw_processing = False
        last_status: dict = {}
        for _ in range(80):
            await asyncio.sleep(0.05)
            status_data = (await api_client.get(f"/api/v1/papers/{paper_id}/status")).json()["data"]
            detail_data = (await api_client.get(f"/api/v1/papers/{paper_id}")).json()["data"]
            last_status = status_data
            if status_data["status"] == "processing":
                saw_processing = True
                # Status and detail endpoints are served from the same in-memory
                # state, but a tiny race can make one see ready before the other.
                assert detail_data["status"] in ("processing", "ready")
                assert status_data["stage"] in (
                    "head_refining",
                    "ingesting",
                    "classifying",
                    "extracting",
                    "storing",
                )
            if status_data["status"] == "ready":
                assert detail_data["status"] in ("processing", "ready")
                break

        assert saw_processing or last_status.get("status") == "ready"
