# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

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
    from backend.rag.vector_store import VectorStore
    from backend.rag.vector_store_wiring import bind_vector_store, reset_vector_store
    from backend.services.paper_service import get_paper_service
    from backend.startup.profile_validation import probe_reranker_connectivity

    settings = get_settings()
    await probe_reranker_connectivity(settings)

    register_pipeline_finalized_handlers()
    from backend.events.bus import install_default_event_bus_hooks

    install_default_event_bus_hooks()
    from backend.repositories import register_main_event_loop

    register_main_event_loop(asyncio.get_running_loop())
    from backend.startup.asyncio_debug import configure_asyncio_block_detector

    configure_asyncio_block_detector(asyncio.get_running_loop())
    # Schema must be applied out-of-band: ``uv run python scripts/init_db.py``.
    await get_paper_service().bootstrap()

    from backend.pipeline.processing_watchdog import (
        reconcile_processing_on_startup,
        start_processing_watchdog,
        stop_processing_watchdog,
    )
    from backend.rag.indexing_watchdog import (
        reconcile_indexing_on_startup,
        start_indexing_watchdog,
        stop_indexing_watchdog,
    )
    from backend.rag.wipe_vector_sweep import (
        reconcile_vector_cleanup_on_startup,
        start_vector_cleanup_poller,
        stop_vector_cleanup_poller,
    )

    # P13: promote orphaned INDEXING rows left by a previous process, then start
    # the out-of-loop macro watchdog (dedicated OS thread + sync SQLAlchemy scans;
    # must not run_async onto the FastAPI loop — main-loop starvation would stall heal).
    await reconcile_indexing_on_startup()
    start_indexing_watchdog()
    # Processing orphan heal: leftover pending/processing → failed, then wall-clock daemon.
    await reconcile_processing_on_startup()
    start_processing_watchdog()
    # Wave-2 outbox: re-arm / immediately scrub vector_cleanup_queue after restart,
    # then poll due rows so failed compensate retries without waiting for next reboot.
    await reconcile_vector_cleanup_on_startup()
    start_vector_cleanup_poller()

    preconfigured = getattr(app.state, "hybrid_retriever", None)
    if preconfigured is not None:
        bind_hybrid_retriever(preconfigured)
        attached = getattr(preconfigured, "vector_store", None)
        if isinstance(attached, VectorStore):
            bind_vector_store(attached)
            app.state.vector_store = attached
        logger.info("HybridRetriever reused from pre-configured app.state")
    else:
        store = VectorStore(paper_service=get_paper_service())
        bind_vector_store(store)
        app.state.vector_store = store
        retriever = create_hybrid_retriever(vector_store=store)
        app.state.hybrid_retriever = retriever
        bind_hybrid_retriever(retriever)
        logger.info("VectorStore + HybridRetriever initialized and bound to app.state")
    try:
        yield
    finally:
        from backend.events.bus import stop_event_bus_worker

        stop_vector_cleanup_poller()
        stop_processing_watchdog()
        stop_indexing_watchdog()
        stop_event_bus_worker()
        register_main_event_loop(None)
        reset_vector_store()
        reset_hybrid_retriever()
        if hasattr(app.state, "vector_store"):
            delattr(app.state, "vector_store")
        if hasattr(app.state, "hybrid_retriever"):
            delattr(app.state, "hybrid_retriever")


def create_app() -> FastAPI:
    from backend.startup.profile_validation import run_startup_profile_validation

    settings = get_settings()
    run_startup_profile_validation(settings)
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
    # After API/OpenAPI routes so SPA catch-all does not shadow them.
    from backend.startup.spa_static import mount_frontend_spa

    mount_frontend_spa(app)
    return app


app = create_app()
