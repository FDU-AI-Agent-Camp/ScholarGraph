# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""First-class Patrol RAG degradation contracts and helpers.

Explicit ``degradation_profile`` on ``PatrolInsight`` is the source of truth.
Legacy ``meta.patrol_rag_context_degraded`` is mirrored for backward compatibility.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.schemas.patrol import (
    PatrolDegradationComponent,
    PatrolDegradationProfile,
    PatrolDegradationReason,
    PatrolDegradationSeverity,
    PatrolReport,
)

# Legacy meta key kept for older FE / tooling until fully migrated.
RAG_DEGRADED_META_KEY = "patrol_rag_context_degraded"

_REASON_PRIORITY: dict[PatrolDegradationReason, int] = {
    PatrolDegradationReason.QUERY_FAILED: 1,
    PatrolDegradationReason.INDEX_NOT_READY: 2,
    PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE: 3,
}

_SEVERITY_BY_REASON: dict[PatrolDegradationReason, PatrolDegradationSeverity] = {
    PatrolDegradationReason.INDEX_NOT_READY: PatrolDegradationSeverity.WARNING,
    PatrolDegradationReason.QUERY_FAILED: PatrolDegradationSeverity.WARNING,
    PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE: PatrolDegradationSeverity.ERROR,
}


def make_degradation_profile(
    reason_code: PatrolDegradationReason,
    affected_papers: list[str],
    *,
    timestamp: datetime | None = None,
) -> PatrolDegradationProfile:
    """Build a typed degradation profile for RAG context thinning."""
    unique_papers = list(dict.fromkeys(affected_papers))
    return PatrolDegradationProfile(
        component=PatrolDegradationComponent.RAG_CONTEXT,
        reason_code=reason_code,
        affected_papers=unique_papers,
        severity=_SEVERITY_BY_REASON[reason_code],
        timestamp=timestamp or datetime.now(UTC),
    )


def merge_degradation_profiles(
    current: PatrolDegradationProfile | None,
    incoming: PatrolDegradationProfile | None,
) -> PatrolDegradationProfile | None:
    """Merge two profiles, keeping the higher-priority reason and union of papers."""
    if current is None:
        return incoming
    if incoming is None:
        return current

    preferred_reason = current.reason_code
    if _REASON_PRIORITY[incoming.reason_code] > _REASON_PRIORITY[current.reason_code]:
        preferred_reason = incoming.reason_code

    merged_papers = list(dict.fromkeys([*current.affected_papers, *incoming.affected_papers]))
    return make_degradation_profile(preferred_reason, merged_papers, timestamp=incoming.timestamp)


def legacy_meta_from_profile(profile: PatrolDegradationProfile | None) -> dict[str, object]:
    """Mirror a first-class profile into legacy ``meta`` for older consumers."""
    if profile is None:
        return {}
    return {
        RAG_DEGRADED_META_KEY: {
            "reason": profile.reason_code.value.lower(),
            "reason_code": profile.reason_code.value,
            "paper_ids": list(profile.affected_papers),
            "severity": profile.severity.value,
            "component": profile.component.value,
            "timestamp": profile.timestamp.isoformat().replace("+00:00", "Z"),
        },
    }


def report_has_rag_degradation(report: PatrolReport) -> bool:
    """True when any insight carries an explicit RAG degradation profile."""
    return any(insight.is_degraded or insight.degradation_profile is not None for insight in report.insights)


def is_vector_store_connectivity_error(exc: BaseException) -> bool:
    """True for store-down failures (refused / unreachable).

    ``TimeoutError`` is intentionally excluded so query-path timeouts map to
    ``QUERY_FAILED`` rather than ``VECTOR_STORE_UNAVAILABLE``.
    """
    if isinstance(exc, TimeoutError):
        return False
    if isinstance(exc, ConnectionError):
        return True
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    connectivity_tokens = ("connection refused", "unavailable", "unreachable", "refused")
    return any(token in name or token in message for token in connectivity_tokens)


def is_vector_store_probe_outage(exc: BaseException) -> bool:
    """exists() probe failures that indicate the store is unreachable."""
    return is_vector_store_connectivity_error(exc) or isinstance(exc, TimeoutError)
