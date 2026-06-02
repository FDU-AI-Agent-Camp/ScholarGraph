"""FastAPI dependencies."""

from uuid import uuid4

from fastapi import Header

from backend.config import Settings, get_settings
from backend.services.paper_service import PaperService, get_paper_service


def get_request_id(x_request_id: str | None = Header(default=None, alias="X-Request-Id")) -> str:
    return x_request_id or str(uuid4())


def get_settings_dep() -> Settings:
    return get_settings()


def get_paper_service_dep() -> PaperService:
    return get_paper_service()
