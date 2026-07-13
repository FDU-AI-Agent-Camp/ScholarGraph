"""Tests for structured health telemetry builders."""

from __future__ import annotations

from backend.api.health_telemetry import (
    build_enriched_health_payload,
    build_patrol_service_health,
    resolve_aggregate_health_status,
    resolve_reranker_status,
)
from backend.config import Settings


def test_reranker_status_ready_when_configured_live() -> None:
    settings = Settings(
        _env_file=None,
        app_profile="demo",
        llm_mode="live",
        reranker_enabled=True,
        reranker_model="bge-reranker-large",
    )
    assert resolve_reranker_status(settings) == "READY"


def test_reranker_status_disabled_fallback_in_live() -> None:
    settings = Settings(_env_file=None, llm_mode="live", reranker_enabled=False)
    assert resolve_reranker_status(settings) == "DISABLED_FALLBACK_ACTIVE"


def test_patrol_service_degraded_payload_includes_warnings() -> None:
    settings = Settings(
        _env_file=None,
        app_profile="ci",
        llm_mode="live",
        reranker_enabled=False,
        scholargraph_api_key="k",
    )
    patrol = build_patrol_service_health(settings)
    assert patrol["status"] == "degraded"
    assert patrol["claim_rq_funnel_enabled"] is False
    assert patrol["reranker_status"] == "DISABLED_FALLBACK_ACTIVE"
    assert patrol["warnings"]
    assert any("Reranker is disabled" in item for item in patrol["warnings"])


def test_aggregate_status_healthy_for_mock_profile() -> None:
    settings = Settings(_env_file=None, app_profile="ci", llm_mode="mock", reranker_enabled=False)
    patrol = build_patrol_service_health(settings)
    assert patrol["status"] == "fully_functional"
    assert resolve_aggregate_health_status(patrol) == "healthy"


def test_enriched_payload_exposes_components() -> None:
    settings = Settings(
        _env_file=None,
        app_profile="demo",
        llm_mode="live",
        reranker_enabled=True,
        reranker_model="bge-reranker-large",
        scholargraph_api_key="k",
    )
    payload = build_enriched_health_payload(settings, version="1.0.0", grobid_connected=False)
    assert payload["status"] == "healthy"
    assert payload["components"]["patrol_service"]["reranker_status"] == "READY"
    assert payload["patrol_claim_rq_funnel_enabled"] is True
