"""Availability helpers for ``@pytest.mark.demo_profile_check`` admission tests."""

from __future__ import annotations

from backend.config import Settings, get_settings


def demo_profile_check_available(settings: Settings | None = None) -> bool:
    """Return True when demo-profile live funnel prerequisites are satisfied."""
    resolved = settings or get_settings()
    if resolved.app_profile != "demo":
        return False
    if resolved.is_llm_mock:
        return False
    if not resolved.reranker_enabled:
        return False
    if not resolved.reranker_model.strip():
        return False
    if not resolved.patrol_claim_rq_funnel_enabled():
        return False
    if resolved.embedding_provider != "ollama" and not resolved.embedding_api_key_effective.strip():
        return False
    return True


def demo_profile_skip_reason(settings: Settings | None = None) -> str:
    return (
        "demo_profile_check unavailable: set APP_PROFILE=demo, LLM_MODE=live, "
        "RERANKER_ENABLED=true, RERANKER_MODEL, and embedding API credentials"
    )
