"""HTTP: POST /api/v1/papers — upload, validation, and INGEST_FAILED red paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.services.paper_service import MAX_UPLOAD_BYTES, get_paper_service
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope

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
    assert "轮询" in data["message"]


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
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("poll-me.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]

    status = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert status.status_code == 200
    assert_success_envelope(status.json())
    data = status.json()["data"]
    assert data["status"] == "pending"
    assert data["percent"] == 0
    assert data.get("stage") is None


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
    before = len(get_paper_service()._papers)

    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert_error_envelope(response.json(), code="INGEST_FAILED")
    assert "PDF" in response.json()["error"]["message"]
    assert len(get_paper_service()._papers) == before


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
