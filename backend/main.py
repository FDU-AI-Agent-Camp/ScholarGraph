"""FastAPI application factory."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.handlers import register_exception_handlers
from backend.api.router import api_router
from backend.config import get_settings
from backend.constants import API_VERSION

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize long-lived RAG clients once; routes reuse via ``app.state``."""
    from backend.events.pipeline_finalized_handlers import register_pipeline_finalized_handlers
    from backend.rag.hybrid_retriever import bind_hybrid_retriever, create_hybrid_retriever, reset_hybrid_retriever
    from backend.services.paper_service import get_paper_service

    register_pipeline_finalized_handlers()
    from backend.events.bus import install_default_event_bus_hooks

    install_default_event_bus_hooks()
    from backend.repositories import register_main_event_loop

    register_main_event_loop(asyncio.get_running_loop())
    # Schema must be applied out-of-band: ``uv run python scripts/init_db.py``.
    await get_paper_service().bootstrap()

    preconfigured = getattr(app.state, "hybrid_retriever", None)
    if preconfigured is not None:
        bind_hybrid_retriever(preconfigured)
        logger.info("HybridRetriever reused from pre-configured app.state")
    else:
        retriever = create_hybrid_retriever()
        app.state.hybrid_retriever = retriever
        bind_hybrid_retriever(retriever)
        logger.info("HybridRetriever initialized and bound to app.state")
    try:
        yield
    finally:
        register_main_event_loop(None)
        reset_hybrid_retriever()
        if hasattr(app.state, "hybrid_retriever"):
            delattr(app.state, "hybrid_retriever")


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_llm_mock:
        logger.warning(
            "LLM_MODE=mock — 云服务尚未接入；问答 / 巡检 / 抽取使用本地 Mock 响应（见 GET /api/v1/health）",
        )
    for patrol_warning in settings.patrol_config_warnings():
        logger.warning("patrol_config: %s", patrol_warning)
    app = FastAPI(
        title="ScholarGraph API",
        version=API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
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
