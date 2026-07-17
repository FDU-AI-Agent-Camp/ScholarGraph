# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""API / contract layer: pagination extrema + response Schema + upload hygiene.

Maps to the full-stack matrix §2 (Contract Level).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.schemas.paper import PaperStatusData
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope

VALID_PDF = b"%PDF-1.4\n% contract boundary"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "expected_status"),
    [
        ({"limit": 0}, 422),
        ({"limit": -1}, 422),
        ({"limit": 2**31 - 1}, 422),
        ({"offset": -1}, 422),
        ({"limit": 1, "offset": 0}, 200),
        ({"limit": 100}, 200),
    ],
)
async def test_list_papers_boundary_value_injection(
    api_client: AsyncClient,
    persistence_env,
    params: dict[str, int],
    expected_status: int,
) -> None:
    response = await api_client.get("/api/v1/papers", params=params)
    assert response.status_code == expected_status
    if expected_status == 200:
        assert_success_envelope(response.json())
        data = response.json()["data"]
        assert "items" in data and "total" in data
        assert data["limit"] == params.get("limit", 20)
        assert data["offset"] == params.get("offset", 0)


@pytest.mark.asyncio
async def test_paper_status_response_matches_pydantic_contract(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("contract.pdf", VALID_PDF, "application/pdf")},
    )
    assert create.status_code == 201
    paper_id = create.json()["data"]["paper_id"]

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert_success_envelope(body)
    snapshot = PaperStatusData.model_validate(body["data"])
    assert snapshot.paper_id == paper_id
    # Forbid free-form top-level keys outside DataResponse envelope.
    assert set(body.keys()) <= {"data", "meta"}
    assert "request_id" in body["meta"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("broken.pdf", b"not-a-pdf", "application/pdf"),
        ("empty.pdf", b"", "application/pdf"),
        ("notes.txt", b"plain text", "text/plain"),
    ],
)
async def test_upload_rejected_payloads_leave_no_orphan_temp_files(
    api_client: AsyncClient,
    upload_dir: Path,
    filename: str,
    content: bytes,
    content_type: str,
) -> None:
    before = {path.name for path in upload_dir.glob("*.pdf")}
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code in {400, 422}
    if response.status_code == 400:
        assert_error_envelope(response.json(), code="INGEST_FAILED")
    assert response.status_code != 500
    after = {path.name for path in upload_dir.glob("*.pdf")}
    assert after == before
