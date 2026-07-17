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
    from backend.services.paper_service import get_paper_service
    from backend.services.pipeline_completion_service import get_pipeline_completion_service
    from backend.services.pipeline_status_service import get_pipeline_status_service

    get_settings.cache_clear()
    reset_database_caches()
    get_paper_repository.cache_clear()
    get_pipeline_repository.cache_clear()
    reset_pipeline_sync_engine()
    get_paper_service.cache_clear()
    get_graph_persistence_service.cache_clear()
    get_pipeline_status_service.cache_clear()
    get_pipeline_completion_service.cache_clear()
    reset_event_bus_cache()
