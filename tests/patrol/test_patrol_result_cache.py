"""Patrol result-cache key fingerprint and healthy-only TTL."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from backend.patrol.result_cache import (
    PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS,
    InMemoryPatrolResultCache,
    build_patrol_cache_key,
    collect_patrol_paper_fingerprint,
)
from backend.schemas.patrol import PatrolMode, PatrolReport
from backend.services.patrol_service import PatrolService


def _empty_report(mode: PatrolMode = PatrolMode.METHOD_OVERLAP) -> PatrolReport:
    from datetime import UTC, datetime

    return PatrolReport(
        mode=mode,
        paper_ids=["a", "b"],
        insights=[],
        generated_at=datetime(2026, 7, 14, tzinfo=UTC),
    )


def test_build_patrol_cache_key_includes_fingerprint() -> None:
    key = build_patrol_cache_key(
        ["a", "b"],
        PatrolMode.METHOD_OVERLAP,
        paper_fingerprint="a@2/run-1;b@2/run-9",
    )
    assert key == "patrol:method_overlap:a,b:fp=a@2/run-1;b@2/run-9"


def test_cache_set_always_uses_healthy_ttl() -> None:
    cache = InMemoryPatrolResultCache()
    ttl = cache.set("k", _empty_report())
    assert ttl == PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS
    assert cache.inspect_ttl("k") == PATROL_HEALTHY_CACHE_MAX_AGE_SECONDS


def test_collect_fingerprint_uses_graph_version_and_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    paper_service = MagicMock()
    paper_service.get_pipeline_graph_version.side_effect = lambda pid: {"p1": "3", "p2": "3"}[pid]
    paper_service.get_active_run_id.side_effect = lambda pid: {"p1": "run-a", "p2": None}[pid]
    monkeypatch.setattr(
        "backend.services.paper_service.get_paper_service",
        lambda: paper_service,
    )
    assert collect_patrol_paper_fingerprint(["p1", "p2"]) == "p1@3/run-a;p2@3/-"


def test_collect_fingerprint_tolerates_missing_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    paper_service = MagicMock()
    paper_service.get_pipeline_graph_version.side_effect = KeyError("paper not found")
    paper_service.get_active_run_id.return_value = None
    monkeypatch.setattr(
        "backend.services.paper_service.get_paper_service",
        lambda: paper_service,
    )
    assert collect_patrol_paper_fingerprint(["ghost"]) == "ghost@missing/-"


@pytest.mark.asyncio
async def test_reextract_fingerprint_change_bypasses_stale_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """After graph_version / index_run bumps, cache must not return the prior report."""
    from backend.schemas.patrol import PatrolInsight, PatrolInsightStatus

    calls = {"n": 0}
    fingerprint = {"value": "a@1/r1;b@1/r1"}

    async def _fake_run(paper_ids, mode, **_kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return PatrolReport(
            mode=mode,
            paper_ids=list(paper_ids),
            generated_at=_empty_report().generated_at,
            insights=[
                PatrolInsight(
                    insight_id=f"ins-{calls['n']}",
                    title="t",
                    summary=f"generation-{calls['n']}",
                    status=PatrolInsightStatus.READY,
                    paper_ids=list(paper_ids),
                    node_refs=[],
                    is_degraded=False,
                ),
            ],
        )

    monkeypatch.setattr("backend.services.patrol_service.patrol_run", _fake_run)
    service = PatrolService(
        result_cache=InMemoryPatrolResultCache(),
        cache_enabled=True,
        paper_fingerprint_fn=lambda _ids: fingerprint["value"],
    )

    first = await service.run_patrol(["a", "b"], PatrolMode.LENS_CLASH)
    second = await service.run_patrol(["a", "b"], PatrolMode.LENS_CLASH)
    assert second.insights[0].summary == first.insights[0].summary
    assert calls["n"] == 1

    fingerprint["value"] = "a@2/r2;b@2/r2"
    third = await service.run_patrol(["a", "b"], PatrolMode.LENS_CLASH)
    assert third.insights[0].summary == "generation-2"
    assert calls["n"] == 2
