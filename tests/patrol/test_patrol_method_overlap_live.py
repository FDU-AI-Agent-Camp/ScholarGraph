# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Live automation regression for method_overlap (``@pytest.mark.live_patrol_logic``).

Architecture::

    patrol_method_overlap_golden.json
              │
              ▼
    Pytest Live Runner (parametrized)
      1. Setup: hydrate in-memory subgraph + real EmbeddingClient
      2. Execute: full method_overlap funnel
      3. Assert: dual-layer (primary + drift guard)

Requires ``LLM_MODE=live`` and embedding API credentials (or Ollama).
Excluded from default CI via ``live_patrol_logic`` marker.
"""

from __future__ import annotations

import os

import pytest
from backend.config import get_settings
from backend.llm.embeddings import reset_embedding_client_cache
from tests.fixtures.patrol_method_overlap_golden import (
    GoldenExpectedStatus,
    MethodOverlapGoldenPair,
    golden_set_path,
    load_method_overlap_golden_set,
)
from tests.patrol.conftest import patch_patrol_settings
from tests.patrol.method_overlap_live_engine import (
    build_live_patrol_context,
    execute_method_overlap_funnel,
    format_live_failure,
    live_embedding_available,
    run_live_dual_assertion,
)

pytestmark = pytest.mark.live_patrol_logic


@pytest.fixture
def live_patrol_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject production embedding path — no golden stub clients."""
    monkeypatch.setenv("LLM_MODE", os.environ.get("LLM_MODE", "live"))
    if not os.environ.get("SCHOLARGRAPH_API_KEY") and os.environ.get("EMBEDDING_API_KEY"):
        monkeypatch.setenv("SCHOLARGRAPH_API_KEY", os.environ["EMBEDDING_API_KEY"])
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True)
    reset_embedding_client_cache()


@pytest.fixture
def require_live_patrol_embedding(live_patrol_env: None) -> None:
    if not live_embedding_available():
        pytest.skip("live_patrol_logic unavailable: set LLM_MODE=live and embedding API credentials")


def test_method_overlap_golden_set_v2_schema() -> None:
    golden = load_method_overlap_golden_set()
    assert golden_set_path().is_file()
    assert golden.schema_version == 3
    assert len(golden.pairs) == 3
    assert golden.pairs[1].expectation.drift_guard is not None
    assert golden.pairs[1].expectation.drift_guard.enabled is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pair",
    load_method_overlap_golden_set().pairs,
    ids=lambda item: item.id,
)
async def test_method_overlap_golden_pair_live_regression(
    pair: MethodOverlapGoldenPair,
    require_live_patrol_embedding: None,
) -> None:
    """Live dual-layer regression: funnel outcome + semantic drift guard."""
    ctx = build_live_patrol_context(pair)
    assert not ctx.embedding_client.is_mock

    insight = await execute_method_overlap_funnel(ctx)
    report = await run_live_dual_assertion(ctx, insight)

    assert report.passed, format_live_failure(report)


@pytest.mark.asyncio
async def test_live_runner_wires_real_threshold_from_settings(
    require_live_patrol_embedding: None,
) -> None:
    """Smoke: live context reads PATROL_SEMANTIC_THRESHOLD for drift guard."""
    pair = next(
        pair
        for pair in load_method_overlap_golden_set().pairs
        if pair.expectation.expected_status == GoldenExpectedStatus.INSUFFICIENT_DATA
    )
    ctx = build_live_patrol_context(pair)
    assert ctx.settings.patrol_semantic_threshold > 0.0
    assert get_settings().patrol_semantic_threshold == ctx.settings.patrol_semantic_threshold
