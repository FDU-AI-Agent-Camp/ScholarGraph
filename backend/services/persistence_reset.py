# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Clear cached settings, DB engines, repositories, and service singletons."""

from __future__ import annotations


def reset_persistence_singletons() -> None:
    """Clear cached settings, DB engines, repositories, and service singletons."""
    from backend.config import get_settings
    from backend.db.base import reset_database_caches
    from backend.events.bus import reset_event_bus_cache
    from backend.repositories.paper_repository import get_paper_repository
    from backend.repositories.pipeline_repository import get_pipeline_repository
    from backend.repositories.pipeline_sync import reset_pipeline_sync_engine
    from backend.services.graph_persistence_service import get_graph_persistence_service
    from backend.services.head_refine_coordinator import get_head_refine_coordinator
    from backend.services.paper_delete_service import get_paper_delete_service
    from backend.services.paper_pipeline_ops import get_paper_pipeline_ops_service
    from backend.services.paper_service_wiring import reset_paper_service
    from backend.services.paper_warning_service import get_paper_warning_service
    from backend.services.pipeline_completion_service import get_pipeline_completion_service
    from backend.services.pipeline_status_service import get_pipeline_status_service
    from backend.services.reextract_service import get_reextract_service

    get_settings.cache_clear()
    reset_database_caches()
    get_paper_repository.cache_clear()
    get_pipeline_repository.cache_clear()
    reset_pipeline_sync_engine()
    reset_paper_service()
    get_paper_delete_service.cache_clear()
    get_reextract_service.cache_clear()
    get_paper_warning_service.cache_clear()
    get_head_refine_coordinator.cache_clear()
    get_paper_pipeline_ops_service.cache_clear()
    get_graph_persistence_service.cache_clear()
    get_pipeline_status_service.cache_clear()
    get_pipeline_completion_service.cache_clear()
    reset_event_bus_cache()
    from backend.rag.vector_store_wiring import reset_vector_store

    reset_vector_store()
