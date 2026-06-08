"""G.6 API gate: OpenAPI + fixtures + HTTP contract for classify_warnings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from backend.agents.classifier_constants import CLASSIFIER_HEURISTIC_FALLBACK_CODE
from backend.main import app
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
FIXTURES_DIR = REPO_ROOT / "docs" / "api" / "fixtures"


def _openapi_schema_properties(spec: dict, schema_name: str) -> dict:
    schema = spec["components"]["schemas"][schema_name]
    if "properties" in schema:
        return schema["properties"]
    merged: dict = {}
    for item in schema.get("allOf", ()):
        if "properties" in item:
            merged.update(item["properties"])
    return merged


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_g6_openapi_paper_status_data_classify_warnings_is_string_array() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    field = spec["components"]["schemas"]["PaperStatusData"]["properties"]["classify_warnings"]
    assert field["type"] == "array"
    assert field["items"]["type"] == "string"
    assert "classifier_heuristic_fallback" in field.get("description", "")


def test_g6_openapi_paper_detail_classify_warnings_is_string_array() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    field = _openapi_schema_properties(spec, "PaperDetail")["classify_warnings"]
    assert field["type"] == "array"
    assert field["items"]["type"] == "string"


def test_g6_classify_fallback_fixtures_validate_against_pydantic() -> None:
    status_payload = json.loads((FIXTURES_DIR / "paper-status-classify-fallback.json").read_text(encoding="utf-8"))
    detail_payload = json.loads((FIXTURES_DIR / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))

    PaperStatusData.model_validate(status_payload["data"])
    PaperDetail.model_validate(detail_payload["data"])


@pytest.mark.asyncio
async def test_g6_api_status_fixture_envelope_matches_http(api_client: AsyncClient) -> None:
    expected = json.loads((FIXTURES_DIR / "paper-status-classify-fallback.json").read_text(encoding="utf-8"))["data"]
    paper_id = expected["paper_id"]
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="fixture parity",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
    )
    get_pipeline_status_service().mark_ready(paper_id)
    get_paper_service().record_classify_warnings(paper_id, expected["classify_warnings"])

    response = await api_client.get(f"/api/v1/papers/{paper_id}/status")

    assert response.status_code == 200
    assert response.json()["data"]["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_g6_api_detail_fixture_envelope_matches_http(api_client: AsyncClient) -> None:
    expected = json.loads((FIXTURES_DIR / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))["data"]
    paper_id = expected["paper_id"]
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail.model_validate(
        {
            **expected,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )
    get_pipeline_status_service().mark_ready(paper_id)
    get_paper_service().record_classify_warnings(paper_id, expected["classify_warnings"])

    response = await api_client.get(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classify_warnings"] == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
    assert set(data["classification"].keys()) == {"paradigm", "confidence", "reason"}
