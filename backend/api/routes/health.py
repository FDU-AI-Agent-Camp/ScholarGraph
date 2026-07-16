"""Health check endpoint."""

from fastapi import APIRouter, Depends

from backend.api.deps import get_request_id
from backend.api.health_telemetry import build_enriched_health_payload
from backend.api.responses import success
from backend.config import get_settings
from backend.constants import API_VERSION
from backend.ingest.grobid_client import check_grobid_isalive

router = APIRouter()


@router.get("/health")
async def health(request_id: str = Depends(get_request_id)) -> dict:
    """Liveness probe with enriched Patrol / Reranker configuration telemetry."""
    settings = get_settings()
    grobid_connected = await check_grobid_isalive(settings=settings)
    payload = build_enriched_health_payload(
        settings,
        version=API_VERSION,
        grobid_connected=grobid_connected,
    )
    return success(payload, request_id)
