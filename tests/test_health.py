"""Smoke tests for API v1 health endpoint."""

from backend.main import app
from httpx import ASGITransport, AsyncClient


async def test_health_returns_ok_envelope() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] in {"healthy", "degraded"}
    assert body["data"]["version"] == "1.0.0"
    assert body["data"]["app_profile"] == "ci"
    assert "components" in body["data"]
    assert body["data"]["components"]["patrol_service"]["reranker_status"] in {
        "READY",
        "DISABLED_FALLBACK_ACTIVE",
        "MISCONFIGURED",
        "MOCK_LOCAL",
    }
    assert body["data"]["llm_mode"] in {"mock", "live"}
    assert body["data"]["llm_connected"] == (body["data"]["llm_mode"] == "live")
    assert "llm_note" in body["data"]
    assert "grobid_url" in body["data"]
    assert isinstance(body["data"]["grobid_connected"], bool)
    assert "grobid_note" in body["data"]
    assert "request_id" in body["meta"]
