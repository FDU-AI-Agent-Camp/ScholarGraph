"""API response envelope models (aligned with OpenAPI)."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Meta(BaseModel):
    request_id: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class DataResponse(BaseModel, Generic[T]):
    data: T
    meta: Meta


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int
