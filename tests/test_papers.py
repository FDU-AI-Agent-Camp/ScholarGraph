"""Paper API smoke tests."""

from httpx import ASGITransport, AsyncClient

from backend.main import app


async def test_list_papers_returns_fixture_seed() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] >= 1
    assert len(body["data"]["items"]) >= 1


async def test_get_hss_graph_when_ready() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["paper_id"] == "hss-001"
    assert len(body["data"]["nodes"]) >= 1
