# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Architecture evolution / chaos matrix for residual-2 main-loop decoupling.

Ship today:
- In-process isolation already proven by ``test_watchdog_works_during_event_loop_starvation``
  (``@pytest.mark.p13_release_gate``) — DB promote via sync OS thread while loop sleeps.
- Static AST assertions below lock that the watchdog thread body never
  ``run_async``-schedules scan work onto the FastAPI loop.

Deferred (marked ``architecture_evolution``, skipped until Redis/Worker land):
- Multi-process Web freeze + external broker ``RagIndexed`` fan-out
- Broker outage / Outbox drain / auto-reconnect
- Distributed idempotency (Redlock) under duplicate paper_id events
- Testcontainers: physical kill of Chroma/Redis mid-flight (see ``tests/chaos/``)

Living chaos catalog: ``tests/chaos/test_chaos_resilience_matrix.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = REPO_ROOT / "backend" / "rag" / "indexing_watchdog.py"
PIPELINE_SYNC = REPO_ROOT / "backend" / "repositories" / "pipeline_sync.py"


def test_sync_watchdog_path_never_run_async_onto_main_loop() -> None:
    """Residual-2 partial harden: out-of-loop heal must stay sync-SQL / facade-sync."""
    watchdog = WATCHDOG.read_text(encoding="utf-8")
    pipeline_sync = PIPELINE_SYNC.read_text(encoding="utf-8")
    assert "scan_and_promote_stuck_indexing_sync()" in watchdog
    assert "run_async(scan_and_promote_stuck_indexing())" not in watchdog
    assert "run_async" not in pipeline_sync
    assert "promote_stuck_indexing_paper_sync" in watchdog
    assert "get_paper_service()" in watchdog


def test_p13_starvation_release_gate_remains_catalogued() -> None:
    """Cross-link the already-shipping chaos proof for main-loop starvation."""
    from tests.rag.test_p13_release_gate_matrix import P13_RELEASE_GATE_CASES

    names = {name for _category, name, _path in P13_RELEASE_GATE_CASES}
    assert "test_watchdog_works_during_event_loop_starvation" in names


@pytest.mark.architecture_evolution
@pytest.mark.skip(reason="Residual 2 evolution: needs Redis/RabbitMQ broker + dedicated RAG worker process")
def test_web_loop_freeze_external_broker_still_delivers_rag_indexed() -> None:
    """Chaos: freeze FastAPI loop; Watchdog/Worker must still consume RagIndexed via broker."""
    raise AssertionError("unreachable until distributed EventBus lands")


@pytest.mark.architecture_evolution
@pytest.mark.skip(reason="Residual 2 evolution: needs broker Outbox + reconnect policy")
def test_broker_outage_fail_safe_and_reconnect_drain() -> None:
    """Broker partition: Web must not 500; backlog drains after reconnect."""
    raise AssertionError("unreachable until distributed EventBus lands")


@pytest.mark.architecture_evolution
@pytest.mark.skip(reason="Residual 2 evolution: needs Redis Redlock across multi-worker processes")
def test_distributed_idempotency_under_duplicate_paper_events() -> None:
    """Concurrent duplicate paper_id events: exactly one heavy I/O winner."""
    raise AssertionError("unreachable until multi-worker locking lands")
