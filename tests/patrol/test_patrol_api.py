"""HTTP integration tests for POST /api/v1/patrol."""

import pytest
from httpx import AsyncClient
from tests.helpers.patrol_graphs import (
    build_hss_graph_without_lens,
    seed_patrol_graphs,
)
from tests.patrol.conftest import assert_api_envelope


@pytest.mark.asyncio
async def test_patrol_api_lens_clash_success(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    seed_patrol_graphs(
        patrol_graph_dir,
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
    assert_api_envelope(body)
    data = body["data"]
    assert data["mode"] == "lens_clash"
    assert data["paper_ids"] == ["hss-001", "hss-002"]
    assert len(data["insights"]) == 1
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-lens-clash-001"
    assert len(insight["node_refs"]) == 2
    assert insight["node_refs"][0]["label"] == "消费社会"
    assert data["generated_at"]


@pytest.mark.asyncio
async def test_patrol_api_defaults_mode_to_lens_clash(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    seed_patrol_graphs(
        patrol_graph_dir,
        {
            "hss-001": ("n_lens_a", "历史制度主义"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["mode"] == "lens_clash"


@pytest.mark.asyncio
async def test_patrol_api_rejects_single_paper_id(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001"], "mode": "lens_clash"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patrol_api_rejects_three_paper_ids(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002", "hss-003"], "mode": "lens_clash"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patrol_api_graph_not_ready_returns_409(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    _ = patrol_graph_dir
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "GRAPH_NOT_READY"


@pytest.mark.asyncio
async def test_patrol_api_insufficient_lens_data_returns_422(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_hss_graph_with_lens

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_without_lens("hss-001"))
    store.save(build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label="公共领域"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PATROL_INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_patrol_api_contradiction_mode_returns_501(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    seed_patrol_graphs(
        patrol_graph_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "contradiction"},
    )
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "PATROL_UNSUPPORTED_MODE"
