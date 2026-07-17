# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Helpers to build success envelopes."""

from typing import Any

from backend.schemas.envelope import DataResponse, Meta, PaginatedData


def success(data: Any, request_id: str) -> dict[str, Any]:
    envelope = DataResponse(data=data, meta=Meta(request_id=request_id))
    return envelope.model_dump(mode="json")


def paginated(
    items: list[Any],
    *,
    total: int,
    offset: int,
    limit: int,
    request_id: str,
) -> dict[str, Any]:
    payload = PaginatedData(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
    return success(payload, request_id)
