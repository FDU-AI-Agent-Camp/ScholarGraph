"""Smoke tests for API v1 health endpoint."""

from backend.main import app
from httpx import ASGITransport, AsyncClient


async def test_health_returns_ok_envelope() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ok"
    assert body["data"]["version"] == "1.0.0"
    assert "request_id" in body["meta"]
