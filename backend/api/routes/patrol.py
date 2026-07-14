"""Patrol routes (BE-4 implements PatrolService logic)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.api.deps import get_request_id
from backend.api.responses import success
from backend.patrol.degradation import (
    PATROL_DEGRADED_CACHE_MAX_AGE_SECONDS,
    report_has_rag_degradation,
)
from backend.schemas.patrol import PatrolMode
from backend.services.patrol_service import PatrolService

router = APIRouter(prefix="/patrol")


class PatrolRequest(BaseModel):
    paper_ids: list[str] = Field(min_length=2, max_length=2)
    mode: PatrolMode = PatrolMode.LENS_CLASH


def get_patrol_service_dep() -> PatrolService:
    from backend.services.patrol_service import get_patrol_service

    return get_patrol_service()


@router.post("", response_model=None)
async def run_patrol_route(
    body: PatrolRequest,
    request_id: str = Depends(get_request_id),
    service: PatrolService = Depends(get_patrol_service_dep),
) -> dict | JSONResponse:
    """Run patrol across two ready papers."""
    report = await service.run_patrol(body.paper_ids, body.mode)
    envelope = success(report, request_id)
    if report_has_rag_degradation(report):
        # Short TTL so thin (degraded) results do not stick in intermediaries.
        return JSONResponse(
            content=envelope,
            headers={
                "Cache-Control": (
                    f"private, max-age={PATROL_DEGRADED_CACHE_MAX_AGE_SECONDS}, must-revalidate"
                ),
            },
        )
    return envelope
