"""HTTP request schemas for multi-scale QA streaming."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class QaStreamRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=50)

    @field_validator("question")
    @classmethod
    def strip_and_require_non_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            msg = "question must not be empty"
            raise ValueError(msg)
        return trimmed
