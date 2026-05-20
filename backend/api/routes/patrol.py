"""Patrol routes (BE-4 implements PatrolService logic)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.deps import get_request_id
from backend.api.responses import success
from backend.services.patrol_service import PatrolService, get_patrol_service

router = APIRouter(prefix="/patrol")


class PatrolRequest(BaseModel):
    paper_ids: list[str] = Field(min_length=1)


def get_patrol_service_dep() -> PatrolService:
    return get_patrol_service()


@router.post("")
async def run_patrol(
    body: PatrolRequest,
    request_id: str = Depends(get_request_id),
    service: PatrolService = Depends(get_patrol_service_dep),
) -> dict:
    report = await service.run_patrol(body.paper_ids)
    return success(report, request_id)
