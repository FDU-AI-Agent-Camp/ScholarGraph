"""Health check endpoint."""

from fastapi import APIRouter, Depends

from backend.api.deps import get_request_id
from backend.api.responses import success
from backend.constants import API_VERSION

router = APIRouter()


@router.get("/health")
async def health(request_id: str = Depends(get_request_id)) -> dict:
    return success({"status": "ok", "version": API_VERSION}, request_id)
