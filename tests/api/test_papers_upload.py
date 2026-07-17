# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""HTTP: POST /api/v1/papers — upload, validation, and INGEST_FAILED red paths."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from backend.services.paper_service import MAX_UPLOAD_BYTES, UPLOAD_QUEUED_MESSAGE, get_paper_service
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope
from tests.helpers.upload_pipeline_mock import mock_http_upload_pipeline_run

VALID_PDF = b"%PDF-1.4\n% ScholarGraph upload test"


@pytest.mark.asyncio
async def test_create_paper_valid_pdf_returns_201_pending_envelope(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("sample.pdf", VALID_PDF, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert data["status"] == "pending"
    assert data["paper_id"]
    assert data["message"] == UPLOAD_QUEUED_MESSAGE


@pytest.mark.asyncio
async def test_create_paper_persists_file_under_upload_dir(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("thesis.pdf", VALID_PDF, "application/pdf")},
    )
    assert response.status_code == 201
    paper_id = response.json()["data"]["paper_id"]

    saved = upload_dir / f"{paper_id}.pdf"
    assert saved.is_file()
    assert saved.read_bytes().startswith(b"%PDF")


@pytest.mark.asyncio
async def test_create_paper_then_get_status_returns_pending(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    """Immediate status read may still be pending before the scheduled task starts."""
    with patch("backend.services.paper_service.schedule_paper_pipeline"):
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("poll-me.pdf", VALID_PDF, "application/pdf")},
        )
        paper_id = create.json()["data"]["paper_id"]

        status = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert status.status_code == 200
    assert_success_envelope(status.json())
    data = status.json()["data"]
    assert data["status"] in ("pending", "processing")
    assert data["percent"] >= 0


@pytest.mark.asyncio
async def test_create_from_upload_schedules_pipeline_once(upload_dir: Path) -> None:
    service = get_paper_service()
    scheduled: list[tuple[str, Path]] = []

    def capture_schedule(paper_id: str, pdf_path: Path) -> None:
        scheduled.append((paper_id, pdf_path))

    with patch(
        "backend.services.paper_service.schedule_paper_pipeline",
        side_effect=capture_schedule,
    ):
        result = await service.create_from_upload(filename="thesis.pdf", content=VALID_PDF)

    assert len(scheduled) == 1
    assert scheduled[0][0] == result.paper_id
    assert scheduled[0][1] == upload_dir / f"{result.paper_id}.pdf"
    assert scheduled[0][1].is_file()


@pytest.mark.asyncio
async def test_create_paper_invalid_upload_does_not_schedule_pipeline(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    with patch("backend.services.paper_service.schedule_paper_pipeline") as mock_schedule:
        response = await api_client.post(
            "/api/v1/papers",
            files={"file": ("notes.txt", b"plain", "text/plain")},
        )
        mock_schedule.assert_not_called()

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_paper_schedules_pipeline_processing(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    _upload_dir, _graph_dir = mock_upload_pipeline_env

    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("pipeline-run.pdf", VALID_PDF, "application/pdf")},
    )
    assert create.status_code == 201
    paper_id = create.json()["data"]["paper_id"]

    seen_processing = False
    final_status = "pending"
    for _ in range(80):
        await asyncio.sleep(0.05)
        status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
        data = status_resp.json()["data"]
        final_status = data["status"]
        if final_status == "processing":
            seen_processing = True
            assert data["stage"] in ("ingesting", "classifying", "extracting", "storing")
            break
        if final_status in ("ready", "ready_with_warnings", "failed"):
            break

    assert seen_processing or final_status in ("ready", "ready_with_warnings", "failed")


@pytest.mark.asyncio
async def test_create_paper_upload_reaches_ready_with_mock_llm(
    api_client: AsyncClient,
    mock_upload_pipeline_env: tuple[Path, Path],
) -> None:
    _upload_dir, graph_dir = mock_upload_pipeline_env

    with mock_http_upload_pipeline_run():
        create = await api_client.post(
            "/api/v1/papers",
            files={"file": ("ready-path.pdf", VALID_PDF, "application/pdf")},
        )
        paper_id = create.json()["data"]["paper_id"]

        final_status = "pending"
        for _ in range(120):
            await asyncio.sleep(0.05)
            status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
            final_status = status_resp.json()["data"]["status"]
            if final_status in ("ready", "ready_with_warnings", "failed"):
                break

        assert final_status == "ready"

    detail = await api_client.get(f"/api/v1/papers/{paper_id}")
    assert detail.json()["data"]["status"] == "ready"

    graph = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph.status_code == 200
    assert_success_envelope(graph.json())

    assert (graph_dir / f"{paper_id}.json").is_file()


@pytest.mark.asyncio
async def test_create_paper_then_graph_before_ready_returns_409(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("early-graph.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]

    graph = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph.status_code == 409
    assert_error_envelope(graph.json(), code="GRAPH_NOT_READY")
    assert "轮询" in graph.json()["error"]["message"]


@pytest.mark.asyncio
async def test_create_paper_non_pdf_extension_returns_400_ingest_failed(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    from backend.repositories.paper_repository import PaperRepository

    _, before = await PaperRepository().list()

    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")
    assert "PDF" in response.json()["error"]["message"]
    _, after = await PaperRepository().list()
    assert after == before


@pytest.mark.asyncio
async def test_create_paper_corrupt_bytes_returns_400_ingest_failed(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("broken.pdf", b"not-a-pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")
    assert "损坏" in response.json()["error"]["message"] or "解析" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_create_paper_oversized_file_returns_400_ingest_failed(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    oversized = b"%PDF" + b"x" * (MAX_UPLOAD_BYTES + 1)
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("huge.pdf", oversized, "application/pdf")},
    )

    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")
    assert "32MB" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_create_paper_empty_file_returns_400_ingest_failed(
    api_client: AsyncClient,
    upload_dir: Path,
) -> None:
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")


@pytest.mark.asyncio
async def test_create_paper_missing_file_field_returns_422(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/v1/papers", data={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_paper_appears_in_list(api_client: AsyncClient, upload_dir: Path) -> None:
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("listed.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]

    listing = await api_client.get("/api/v1/papers")
    assert listing.status_code == 200
    ids = {item["paper_id"] for item in listing.json()["data"]["items"]}
    assert paper_id in ids
