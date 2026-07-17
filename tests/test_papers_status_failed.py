# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper status API — failed fixture mock."""

import json
from pathlib import Path

from backend.main import app
from backend.schemas.paper import FailedDuringStage
from backend.services.paper_service import PaperService
from httpx import ASGITransport, AsyncClient

FAILED_PAPER_ID = "hss-failed-001"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "docs" / "api" / "fixtures"


async def test_get_failed_paper_status_returns_error_fields() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/papers/{FAILED_PAPER_ID}/status")

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["paper_id"] == FAILED_PAPER_ID
    assert data["status"] == "failed"
    assert data["stage"] == "failed"
    assert data["error_code"] == "LLM_JSON_INVALID"
    assert data["failed_during"] == "classifying"
    assert "LLM" in data["message"]
    assert "meta" in body


async def test_list_papers_includes_failed_fixture() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers", params={"status": "failed"})

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    ids = [item["paper_id"] for item in items]
    assert FAILED_PAPER_ID in ids


async def test_get_failed_paper_detail() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/papers/{FAILED_PAPER_ID}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["paper_id"] == FAILED_PAPER_ID
    assert data["status"] == "failed"
    assert data["title"]


async def test_get_failed_status_matches_fixture_file() -> None:
    fixture_path = FIXTURES_DIR / "paper-status-hss-failed-001.json"
    expected = json.loads(fixture_path.read_text(encoding="utf-8"))["data"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/papers/{FAILED_PAPER_ID}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["error_code"] == expected["error_code"]
    assert data["failed_during"] == expected["failed_during"]
    assert data["message"] == expected["message"]
    assert data["percent"] == expected["percent"]


async def test_paper_service_seeds_failed_status_on_startup() -> None:
    service = PaperService()
    status = await service.get_status(FAILED_PAPER_ID)
    assert status.error_code == "LLM_JSON_INVALID"
    assert status.failed_during == FailedDuringStage.CLASSIFYING
