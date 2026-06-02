"""Helpers to build success envelopes."""

from typing import TypeVar

from backend.schemas.envelope import DataResponse, Meta, PaginatedData

T = TypeVar("T")


def success(data: T, request_id: str) -> dict:
    envelope = DataResponse(data=data, meta=Meta(request_id=request_id))
    return envelope.model_dump(mode="json")


def paginated(
    items: list[T],
    *,
    total: int,
    offset: int,
    limit: int,
    request_id: str,
) -> dict:
    payload = PaginatedData(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
    return success(payload, request_id)
