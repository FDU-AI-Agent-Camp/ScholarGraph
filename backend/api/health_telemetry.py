"""Structured health telemetry for Patrol / Reranker configuration disclosure."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from backend.config import Settings

HealthAggregateStatus = Literal["healthy", "degraded"]
PatrolServiceStatus = Literal["fully_functional", "degraded"]
RerankerStatus = Literal["READY", "DISABLED_FALLBACK_ACTIVE", "MISCONFIGURED", "MOCK_LOCAL"]

_RERANKER_DISABLED_WARNING = (
    "Reranker is disabled. Patrol claim evolution will fallback to strict Bi-Encoder thresholds, "
    "which may cause high false-negative rates."
)
_RERANKER_MODEL_MISSING_WARNING = (
    "RERANKER_MODEL is empty while RERANKER_ENABLED=true. Claim evolution rerank stage cannot run."
)


class PatrolServiceHealth(TypedDict, total=False):
    status: PatrolServiceStatus
    claim_rq_funnel_enabled: bool
    reranker_status: RerankerStatus
    active_profile: str | None
    warnings: list[str]


class HealthComponents(TypedDict):
    patrol_service: PatrolServiceHealth


def resolve_reranker_status(settings: Settings) -> RerankerStatus:
    """Map runtime settings to a frontend-friendly reranker state machine value."""
    if settings.is_llm_mock:
        return "MOCK_LOCAL"
    if not settings.reranker_enabled:
        return "DISABLED_FALLBACK_ACTIVE"
    if not settings.reranker_model.strip():
        return "MISCONFIGURED"
    return "READY"


def build_patrol_service_health(settings: Settings) -> PatrolServiceHealth:
    """Build structured patrol_service component for GET /health."""
    reranker_status = resolve_reranker_status(settings)
    funnel_enabled = settings.patrol_claim_rq_funnel_enabled()
    warnings: list[str] = list(settings.patrol_config_warnings())

    if reranker_status == "DISABLED_FALLBACK_ACTIVE" and settings.is_llm_live:
        if _RERANKER_DISABLED_WARNING not in warnings:
            warnings.append(_RERANKER_DISABLED_WARNING)
    if reranker_status == "MISCONFIGURED":
        if _RERANKER_MODEL_MISSING_WARNING not in warnings:
            warnings.append(_RERANKER_MODEL_MISSING_WARNING)

    if settings.is_llm_mock:
        service_status: PatrolServiceStatus = "fully_functional"
    elif funnel_enabled:
        service_status = "fully_functional"
    else:
        service_status = "degraded"

    payload: PatrolServiceHealth = {
        "status": service_status,
        "claim_rq_funnel_enabled": funnel_enabled,
        "reranker_status": reranker_status,
        "active_profile": settings.app_profile,
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


def resolve_aggregate_health_status(patrol_service: PatrolServiceHealth) -> HealthAggregateStatus:
    """Top-level health status for FE guards."""
    if patrol_service.get("status") == "degraded":
        return "degraded"
    return "healthy"


def build_health_components(settings: Settings) -> HealthComponents:
    return {"patrol_service": build_patrol_service_health(settings)}


def build_enriched_health_payload(settings: Settings, *, version: str, grobid_connected: bool) -> dict[str, Any]:
    """Merge legacy health fields with structured ``components`` telemetry."""
    components = build_health_components(settings)
    patrol_service = components["patrol_service"]
    aggregate_status = resolve_aggregate_health_status(patrol_service)
    legacy_warnings = settings.patrol_config_warnings()

    return {
        "status": aggregate_status,
        "version": version,
        "app_profile": settings.app_profile,
        "components": components,
        "llm_mode": settings.llm_mode,
        "llm_connected": settings.is_llm_live,
        "llm_note": (
            "Mock 模式：LLM 云服务尚未接入，问答/巡检返回本地模板。"
            if settings.is_llm_mock
            else "Live 模式：已配置真实 LLM 网关。"
        ),
        "grobid_url": settings.grobid_url,
        "grobid_connected": grobid_connected,
        "grobid_note": (
            "GROBID sidecar 可达，长档 path-B 可用。"
            if grobid_connected
            else "GROBID 不可达：长档 PDF 将降级为 PyMuPDF snippets。"
        ),
        "patrol_claim_rq_funnel_enabled": patrol_service["claim_rq_funnel_enabled"],
        "patrol_config_warnings": legacy_warnings,
        "patrol_note": (
            "claim_evolution 两阶段 RQ 漏斗已启用（粗筛 + Cross-Encoder 精排）。"
            if patrol_service["claim_rq_funnel_enabled"]
            else (
                "claim_evolution 使用严格双塔回退（RERANKER 未完整配置）；"
                "与 CI 金标/合入门禁（reranker_enabled=true）行为不一致，"
                "演示前请设置 RERANKER_ENABLED=true 并填写 RERANKER_MODEL。"
                if settings.is_llm_live
                else "Mock 模式：claim_evolution RQ 配对走本地确定性逻辑，不依赖 Reranker。"
            )
        ),
    }
