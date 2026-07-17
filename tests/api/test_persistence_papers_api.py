# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""API tests for DB-backed paper routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope, assert_success_envelope

VALID_PDF = b"%PDF-1.4\n% persistence api test"


@pytest.mark.asyncio
async def test_list_papers_empty_db_returns_zero_total(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    response = await api_client.get("/api/v1/papers")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []


@pytest.mark.asyncio
async def test_create_paper_writes_db_row(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("api-db.pdf", VALID_PDF, "application/pdf")},
    )
    assert response.status_code == 201
    paper_id = response.json()["data"]["paper_id"]

    detail = await api_client.get(f"/api/v1/papers/{paper_id}")
    assert detail.status_code == 200
    assert_success_envelope(detail.json())
    assert detail.json()["data"]["paper_id"] == paper_id


@pytest.mark.asyncio
async def test_detail_response_does_not_expose_internal_paths(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    create = await api_client.post(
        "/api/v1/papers",
        files={"file": ("paths.pdf", VALID_PDF, "application/pdf")},
    )
    paper_id = create.json()["data"]["paper_id"]
    detail = await api_client.get(f"/api/v1/papers/{paper_id}")
    data = detail.json()["data"]
    assert "pdf_path" not in data
    assert "graph_path" not in data
    assert "head_path" not in data


@pytest.mark.asyncio
async def test_list_papers_pagination_query_params(
    api_client: AsyncClient,
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.services.paper_service.schedule_paper_pipeline", lambda *_a, **_k: None)
    for index in range(3):
        await api_client.post(
            "/api/v1/papers",
            files={"file": (f"p{index}.pdf", VALID_PDF, "application/pdf")},
        )

    response = await api_client.get("/api/v1/papers", params={"offset": 1, "limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] == 3
    assert len(body["data"]["items"]) == 1


@pytest.mark.asyncio
async def test_get_missing_paper_returns_404_envelope(api_client: AsyncClient, persistence_env) -> None:
    response = await api_client.get("/api/v1/papers/does-not-exist-404")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")
