"""Cross-stack merge verification: backend HTTP ↔ docs/api fixtures ↔ FE contract.

After merging feature/frontend, feature/backend/platform, and feature/backend/ingest into develop, these tests
assert live FastAPI responses match the same JSON envelopes the Vue client types and
fixtures expect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.graph.state import STAGE_PERCENT  # noqa: F401 — import before pipeline helpers
from backend.main import app
from backend.schemas.paper import FailedDuringStage, PaperStatusData
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient

from tests.helpers.status_contract import assert_snapshot_matches_contract

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "docs" / "api" / "fixtures"
FAILED_PAPER_ID = "hss-failed-001"
READY_PAPER_ID = "hss-001"
PROCESSING_PAPER_ID = "hss-002"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _assert_api_envelope(body: dict) -> None:
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["meta"].get("request_id"), str)
    assert body["meta"]["request_id"]


def _assert_status_contract(data: dict) -> None:
    snapshot = PaperStatusData.model_validate(data)
    assert_snapshot_matches_contract(snapshot)


def _assert_failed_fixture_parity(data: dict, expected: dict) -> None:
    """Mock failed fixture uses percent=40 (api-contract example); pipeline writes percent=0."""
    from backend.services.pipeline_status_service import validate_failed_error_fields

    snapshot = PaperStatusData.model_validate(data)
    validate_failed_error_fields(
        status=snapshot.status,
        error_code=snapshot.error_code,
        failed_during=snapshot.failed_during,
    )
    assert data["paper_id"] == expected["paper_id"]
    assert data["status"] == expected["status"]
    assert data["stage"] == expected["stage"]
    assert data["error_code"] == expected["error_code"]
    assert data["failed_during"] == expected["failed_during"]
    assert data["message"] == expected["message"]
    assert data["percent"] == expected["percent"]


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_merge_health_for_fe_proxy(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    _assert_api_envelope(body)
    assert body["data"].get("status") == "ok"


@pytest.mark.asyncio
async def test_merge_papers_list_matches_fixture_shape(api_client: AsyncClient) -> None:
    expected = _load_fixture("papers-list.json")
    response = await api_client.get("/api/v1/papers")
    assert response.status_code == 200
    body = response.json()
    _assert_api_envelope(body)

    api_ids = {item["paper_id"] for item in body["data"]["items"]}
    fixture_ids = {item["paper_id"] for item in expected["data"]["items"]}
    assert fixture_ids.issubset(api_ids)
    assert FAILED_PAPER_ID in api_ids
    assert READY_PAPER_ID in api_ids


@pytest.mark.asyncio
async def test_merge_failed_status_matches_docs_fixture(api_client: AsyncClient) -> None:
    expected = _load_fixture("paper-status-hss-failed-001.json")["data"]
    response = await api_client.get(f"/api/v1/papers/{FAILED_PAPER_ID}/status")
    assert response.status_code == 200
    body = response.json()
    _assert_api_envelope(body)
    data = body["data"]
    _assert_failed_fixture_parity(data, expected)
    assert FailedDuringStage(data["failed_during"]) == FailedDuringStage.CLASSIFYING


@pytest.mark.asyncio
async def test_merge_processing_status_matches_per_paper_fixture(api_client: AsyncClient) -> None:
    expected = _load_fixture("paper-status-hss-002.json")["data"]
    response = await api_client.get(f"/api/v1/papers/{PROCESSING_PAPER_ID}/status")
    assert response.status_code == 200
    data = response.json()["data"]
    _assert_status_contract(data)

    assert data["paper_id"] == PROCESSING_PAPER_ID
    assert data["status"] == expected["status"]
    assert data["stage"] == expected["stage"]
    assert data["percent"] == expected["percent"]
    assert data.get("error_code") is None
    assert data.get("failed_during") is None


@pytest.mark.asyncio
async def test_merge_ready_paper_detail_and_graph(api_client: AsyncClient) -> None:
    detail = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}")
    assert detail.status_code == 200
    _assert_api_envelope(detail.json())
    assert detail.json()["data"]["status"] == "ready"

    graph = await api_client.get(f"/api/v1/papers/{READY_PAPER_ID}/graph")
    assert graph.status_code == 200
    graph_body = graph.json()
    _assert_api_envelope(graph_body)
    assert graph_body["data"]["paper_id"] == READY_PAPER_ID
    assert len(graph_body["data"]["nodes"]) >= 1

    expected_graph = _load_fixture("graph-hss.json")["data"]
    assert graph_body["data"]["paradigm"] == expected_graph["paradigm"]


@pytest.mark.asyncio
async def test_merge_patrol_post_envelope(api_client: AsyncClient, tmp_path, monkeypatch) -> None:
    from backend.config import get_settings

    graph_dir = tmp_path / "graphs"
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    from tests.helpers.patrol_graphs import seed_patrol_graphs

    seed_patrol_graphs(
        graph_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 200
    body = response.json()
    _assert_api_envelope(body)
    data = body["data"]
    assert data["mode"] == "lens_clash"
    assert data["paper_ids"] == ["hss-001", "hss-002"]
    assert data["insights"]
    assert data["insights"][0]["insight_id"]
    assert data["insights"][0]["node_refs"]


@pytest.mark.asyncio
async def test_merge_graph_not_ready_returns_409(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{PROCESSING_PAPER_ID}/graph")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GRAPH_NOT_READY"


def test_merge_classifier_labels_corpus_ids_seeded_in_api() -> None:
    """FE 列表与 BE 种子数据应覆盖金标语料 paper_id（ingest 分支合入后）。"""
    from tests.helpers.classifier_labels import load_classifier_labels

    labels = load_classifier_labels()
    listed_ids = set(get_paper_service()._papers.keys())

    for row in labels:
        assert row["paper_id"] in listed_ids
