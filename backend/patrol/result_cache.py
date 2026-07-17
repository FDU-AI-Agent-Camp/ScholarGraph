# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Patrol result cache for healthy (thick-context) reports.

Call sites (``PatrolService``) skip ``set`` for RAG-degraded reports and include
``graph_version`` + active ``index_run_id`` in the cache key so re-extract /
re-index cannot serve a stale 24h entry. In-memory by default; Redis-compatible
interface for a future swap without changing call sites.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from backend.schemas.patrol import PatrolMode, PatrolReport

# Healthy (thick-context) results may be retained longer.
PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
_MISSING_GRAPH_VERSION = "missing"
_MISSING_INDEX_RUN = "-"


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
        """Store a healthy report; return the TTL seconds applied."""
        ttl = PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS
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


def collect_patrol_paper_fingerprint(paper_ids: Sequence[str]) -> str:
    """Build a cache fingerprint from each paper's graph_version + active index run.

    Missing DB rows use placeholders so graph-only / fixture papers still cache
    safely without raising.
    """
    from backend.services.paper_service import get_paper_service

    paper_service = get_paper_service()
    segments: list[str] = []
    for paper_id in paper_ids:
        try:
            graph_version = paper_service.get_pipeline_graph_version(paper_id)
        except KeyError:
            graph_version = _MISSING_GRAPH_VERSION
        run_id = paper_service.get_active_run_id(paper_id) or _MISSING_INDEX_RUN
        segments.append(f"{paper_id}@{graph_version}/{run_id}")
    return ";".join(segments)


def build_patrol_cache_key(
    paper_ids: list[str],
    mode: PatrolMode,
    *,
    paper_fingerprint: str = "",
) -> str:
    ordered = ",".join(paper_ids)
    if paper_fingerprint:
        return f"patrol:{mode.value}:{ordered}:fp={paper_fingerprint}"
    return f"patrol:{mode.value}:{ordered}"
