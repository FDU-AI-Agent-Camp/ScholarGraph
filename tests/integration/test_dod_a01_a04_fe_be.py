"""V1 DoD A-01～A-04 — 前后端联调联试（BE 侧）.

与 ``frontend/src/test/v1-dod-a01-a04.integration.test.ts``、
``v1-dod-a04-fe-be.integration.test.ts`` 成对验收。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.api.conftest import assert_error_envelope, assert_success_envelope

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
READY_ID = "hss-001"
PROCESSING_ID = "hss-002"
FAILED_ID = "hss-failed-001"
VALID_PDF = b"%PDF-1.4\n% A-01-A-04 DoD upload test"


def _load_graph_hss_data() -> dict:
    return json.loads((FIXTURES_DIR / "graph-hss.json").read_text(encoding="utf-8"))["data"]


# ---------------------------------------------------------------------------
# A-01 — 六主屏对应 REST 基座
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a01_health_returns_ok_envelope(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    assert_success_envelope(response.json())


@pytest.mark.asyncio
async def test_a01_papers_list_returns_paginated_envelope(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers")
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    data = body["data"]
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/papers/{READY_ID}",
        f"/api/v1/papers/{READY_ID}/status",
    ],
)
async def test_a01_detail_and_status_endpoints_respond_without_500(api_client: AsyncClient, path: str) -> None:
    response = await api_client.get(path)
    assert response.status_code < 500


@pytest.mark.asyncio
@pytest.mark.usefixtures("graph_hss_fixture_env")
async def test_a01_graph_endpoint_responds_without_500(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{READY_ID}/graph")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# A-02 — 文献库 + 上传
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a02_post_papers_creates_paper_with_201(api_client: AsyncClient, upload_dir: Path) -> None:
    _ = upload_dir
    response = await api_client.post(
        "/api/v1/papers",
        files={"file": ("a04-batch.pdf", VALID_PDF, "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert_success_envelope(body)
    assert body["data"]["paper_id"]


@pytest.mark.asyncio
async def test_a02_list_includes_seeded_ready_paper(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/papers")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    ids = {item["paper_id"] for item in items}
    assert READY_ID in ids


# ---------------------------------------------------------------------------
# A-03 — status 三态
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a03_ready_paper_status_terminal(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{READY_ID}/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ready"
    assert data["message"]


@pytest.mark.asyncio
async def test_a03_processing_paper_status_includes_stage(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/papers/{PROCESSING_ID}/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "processing"
    assert data.get("stage") or data.get("failed_during") is None


    @pytest.mark.asyncio
    async def test_a03_failed_paper_status_surfaces_error_code(api_client: AsyncClient) -> None:
        response = await api_client.get(f"/api/v1/papers/{FAILED_ID}/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "failed"
        assert data["error_code"]
        assert data["failed_during"]
        assert isinstance(data.get("message"), str)
        assert len(data["message"]) >= 4


# ---------------------------------------------------------------------------
# A-04 — 图谱 GET（与 FE G6 / 409 文案对齐）
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("graph_hss_fixture_env")
class TestA04GraphPageContract:
    @pytest.mark.asyncio
    async def test_a04_ready_graph_returns_unified_paper_graph(self, api_client: AsyncClient) -> None:
        response = await api_client.get(f"/api/v1/papers/{READY_ID}/graph")
        assert response.status_code == 200
        body = response.json()
        assert_success_envelope(body)
        data = body["data"]
        expected = _load_graph_hss_data()
        assert data["paper_id"] == READY_ID
        assert data["paradigm"] == expected["paradigm"]
        assert len(data["nodes"]) == len(expected["nodes"])
        node = data["nodes"][0]
        assert "id" in node and "label" in node and "type" in node

    @pytest.mark.asyncio
    async def test_a04_graph_response_is_not_g6_nested_shape(self, api_client: AsyncClient) -> None:
        """B-06/B-07：HTTP 返回扁平 GraphNode，label 不在 data.label 嵌套。"""
        response = await api_client.get(f"/api/v1/papers/{READY_ID}/graph")
        node = response.json()["data"]["nodes"][0]
        nested = node.get("data") or {}
        assert node.get("label")
        assert "label" not in nested

    @pytest.mark.asyncio
    async def test_a04_processing_graph_returns_graph_not_ready(self, api_client: AsyncClient) -> None:
        response = await api_client.get(f"/api/v1/papers/{PROCESSING_ID}/graph")
        assert response.status_code == 409
        body = response.json()
        assert_error_envelope(body, code="GRAPH_NOT_READY")
        assert body["error"]["message"]

    @pytest.mark.asyncio
    async def test_a04_failed_graph_returns_graph_not_ready(self, api_client: AsyncClient) -> None:
        response = await api_client.get(f"/api/v1/papers/{FAILED_ID}/graph")
        assert response.status_code == 409
        assert_error_envelope(response.json(), code="GRAPH_NOT_READY")

    @pytest.mark.asyncio
    async def test_a04_unknown_paper_graph_returns_not_found(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/papers/ghost-a04/graph")
        assert response.status_code == 404
        assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")
