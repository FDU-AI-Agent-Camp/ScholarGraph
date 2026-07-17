# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""In-process fault-injection robustness probe for ``benchmark_patrol`` reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.patrol.circuit_breaker import CircuitState, VectorStoreCircuitBreaker
from backend.patrol.rag_service import PatrolRAGService
from backend.schemas.patrol import PatrolDegradationReason, PatrolMode


@dataclass(slots=True)
class _FaultStore:
    exists_map: dict[str, bool]
    exists_errors: dict[str, BaseException]
    query_error: BaseException | None
    query_calls: list[str]

    async def exists(self, paper_id: str) -> bool:
        if paper_id in self.exists_errors:
            raise self.exists_errors[paper_id]
        return self.exists_map.get(paper_id, False)

    async def query_chunks(self, query: str, *, paper_id: str, top_k: int) -> list[Any]:
        self.query_calls.append(paper_id)
        if self.query_error is not None:
            raise self.query_error
        return []


async def _run_scenario(
    *,
    name: str,
    expected_reason: PatrolDegradationReason,
    exists_map: dict[str, bool] | None = None,
    exists_errors: dict[str, BaseException] | None = None,
    query_error: BaseException | None = None,
    assert_circuit_open: bool = False,
) -> dict[str, Any]:
    store = _FaultStore(
        exists_map=exists_map or {},
        exists_errors=exists_errors or {},
        query_error=query_error,
        query_calls=[],
    )
    breaker = VectorStoreCircuitBreaker(failure_threshold=1, reset_timeout_seconds=60.0)
    service = PatrolRAGService(store, circuit_breaker=breaker)  # type: ignore[arg-type]
    crashed = False
    reason: str | None = None
    http_degraded_ok = False
    try:
        _sections, profile = await service.enrich_context(
            PatrolMode.METHOD_OVERLAP,
            {"stem-001": "q", "stem-002": "q"},
            top_k=3,
        )
        if profile is not None and profile.reason_code == expected_reason:
            http_degraded_ok = True
            reason = profile.reason_code.value
        if assert_circuit_open:
            # Second call must fast-fail without further I/O when breaker OPEN.
            prior_calls = len(store.query_calls)
            _s2, profile2 = await service.enrich_context(
                PatrolMode.METHOD_OVERLAP,
                {"stem-001": "q", "stem-002": "q"},
                top_k=3,
            )
            http_degraded_ok = (
                http_degraded_ok
                and profile2 is not None
                and profile2.reason_code == PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE
                and breaker.state == CircuitState.OPEN
                and len(store.query_calls) == prior_calls
            )
    except Exception as exc:  # noqa: BLE001 — robustness probe must never crash the report
        crashed = True
        reason = type(exc).__name__

    return {
        "scenario": name,
        "expected_reason": expected_reason.value,
        "actual_reason": reason,
        "http_200_degraded": http_degraded_ok,
        "crashed": crashed,
        "circuit_state": breaker.state.value,
    }


async def run_robustness_fault_matrix() -> dict[str, Any]:
    """Execute the three core fault-injection scenarios for benchmark reports."""
    scenarios = [
        await _run_scenario(
            name="index_not_ready",
            expected_reason=PatrolDegradationReason.INDEX_NOT_READY,
            exists_map={"stem-001": False, "stem-002": False},
        ),
        await _run_scenario(
            name="query_timeout",
            expected_reason=PatrolDegradationReason.QUERY_FAILED,
            exists_map={"stem-001": True, "stem-002": True},
            query_error=TimeoutError("vector query timed out"),
        ),
        await _run_scenario(
            name="cluster_down",
            expected_reason=PatrolDegradationReason.VECTOR_STORE_UNAVAILABLE,
            exists_errors={
                "stem-001": ConnectionRefusedError("chroma refused"),
                "stem-002": ConnectionRefusedError("chroma refused"),
            },
            assert_circuit_open=True,
        ),
    ]
    total = len(scenarios)
    degraded_ok = sum(1 for row in scenarios if row["http_200_degraded"])
    crashes = sum(1 for row in scenarios if row["crashed"])
    return {
        "scenarios": scenarios,
        "scenario_count": total,
        "http_200_degrade_rate": round(degraded_ok / total, 4) if total else 0.0,
        "crash_rate": round(crashes / total, 4) if total else 0.0,
        "all_graceful": degraded_ok == total and crashes == 0,
    }
