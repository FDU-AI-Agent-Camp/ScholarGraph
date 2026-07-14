"""Patrol result cache (healthy / thick-context reports only at service call sites).

``PatrolService`` skips ``set`` when a report is RAG-degraded so FE heal polls are
not stuck on a 60s thin snapshot. ``set`` still applies a short TTL if a caller
ever stores a degraded report (defense in depth). In-memory by default;
Redis-compatible interface for a future swap without changing call sites.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from backend.patrol.degradation import (
    PATROL_DEGRADED_CACHE_MAX_AGE_SECONDS,
    report_has_rag_degradation,
)
from backend.schemas.patrol import PatrolMode, PatrolReport

# Healthy (thick-context) results may be retained longer.
PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


class PatrolResultCacheProtocol(Protocol):
    def get(self, cache_key: str) -> PatrolReport | None: ...

    def set(self, cache_key: str, report: PatrolReport) -> int: ...

    def clear(self) -> None: ...


@dataclass(slots=True)
class _CacheEntry:
    report: PatrolReport
    expires_at: float
    ttl_seconds: int


class InMemoryPatrolResultCache:
    """Thread-safe dict cache with injectable clock for TTL tests."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    def get(self, cache_key: str) -> PatrolReport | None:
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                del self._entries[cache_key]
                return None
            return entry.report

    def set(self, cache_key: str, report: PatrolReport) -> int:
        """Store report; return the TTL seconds applied."""
        ttl = (
            PATROL_DEGRADED_CACHE_MAX_AGE_SECONDS
            if report_has_rag_degradation(report)
            else PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS
        )
        with self._lock:
            self._entries[cache_key] = _CacheEntry(
                report=report,
                expires_at=self._clock() + ttl,
                ttl_seconds=ttl,
            )
        return ttl

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def inspect_ttl(self, cache_key: str) -> int | None:
        """Test helper: configured TTL for a live entry."""
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                return None
            return entry.ttl_seconds


def build_patrol_cache_key(paper_ids: list[str], mode: PatrolMode) -> str:
    ordered = ",".join(paper_ids)
    return f"patrol:{mode.value}:{ordered}"
