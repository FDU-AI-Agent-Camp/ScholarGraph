"""FastAPI application factory."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.handlers import register_exception_handlers
from backend.api.router import api_router
from backend.config import get_settings
from backend.constants import API_VERSION

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_llm_mock:
        logger.warning(
            "LLM_MODE=mock — 云服务尚未接入；问答 / 巡检 / 抽取使用本地 Mock 响应（见 GET /api/v1/health）",
        )
    app = FastAPI(
        title="ScholarGraph API",
        version=API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
