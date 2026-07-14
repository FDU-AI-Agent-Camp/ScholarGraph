"""Live automation regression engine for method_overlap golden pairs.

Pipeline (see problems-v2 Part E §2):

1. **Setup** — hydrate in-memory subgraphs from topology blueprint; inject real EmbeddingClient.
2. **Execute** — run full ``build_method_overlap_insight`` funnel (literal + semantic + Plan C).
3. **Assert (primary)** — status, match_type, overlap_label, theta_min.
4. **Assert (drift guard)** — pre-screen cosine must stay below ``PATROL_SEMANTIC_THRESHOLD`` for
   false-positive archetypes even when topology veto yields correct INSUFFICIENT_DATA.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.config import Settings, get_settings
from backend.llm.embeddings import EmbeddingClient, get_embedding_client
from backend.patrol.method_overlap import build_method_overlap_insight, method_nodes
from backend.patrol.method_overlap_semantic import _embed_text_for_node
from backend.patrol.similarity import cosine_similarity_matrix
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.patrol import PatrolInsight
from tests.fixtures.patrol_method_overlap_golden import (
    MethodOverlapGoldenPair,
    evaluate_method_overlap_golden_pair,
    hydrate_patrol_graph_pair,
)

_DRIFT_GUARD_STRICT_ENV = "PATROL_LIVE_DRIFT_GUARD_STRICT"


@dataclass(frozen=True, slots=True)
class LivePatrolContext:
    """Runtime context for one parametrized live golden pair."""

    pair: MethodOverlapGoldenPair
    graphs: dict[str, UnifiedPaperGraph]
    paper_ids: list[str]
    embedding_client: EmbeddingClient
    settings: Settings


@dataclass(frozen=True, slots=True)
class LiveAssertionReport:
    """Dual-layer assertion outcome."""

    primary_passed: bool
    primary_detail: str
    prescreen_cosine: float | None
    drift_passed: bool
    drift_detail: str

    @property
    def passed(self) -> bool:
        return self.primary_passed and self.drift_passed


def live_embedding_available(settings: Settings | None = None) -> bool:
    """Return True when a non-mock embedding backend is configured."""
    resolved = settings or get_settings()
    if resolved.is_llm_mock:
        return False
    if resolved.embedding_provider == "ollama":
        return True
    return bool(resolved.embedding_api_key_effective.strip())


def build_live_patrol_context(
    pair: MethodOverlapGoldenPair,
    *,
    embedding_client: EmbeddingClient | None = None,
    settings: Settings | None = None,
) -> LivePatrolContext:
    """Assemble live runner context: hydrated graphs + production embedding client."""
    client = embedding_client or get_embedding_client()
    if client.is_mock:
        msg = "live_patrol_logic requires a non-mock EmbeddingClient (set LLM_MODE=live and API credentials)"
        raise RuntimeError(msg)

    resolved_settings = settings or get_settings()
    return LivePatrolContext(
        pair=pair,
        graphs=hydrate_patrol_graph_pair(pair),
        paper_ids=[pair.paper_a_id, pair.paper_b_id],
        embedding_client=client,
        settings=resolved_settings,
    )


async def execute_method_overlap_funnel(ctx: LivePatrolContext) -> PatrolInsight:
    """Run the full production method_overlap funnel on hydrated in-memory graphs."""
    insight = await build_method_overlap_insight(
        ctx.graphs,
        ctx.paper_ids,
        embedding_client=ctx.embedding_client,
    )
    if insight is None:
        msg = f"build_method_overlap_insight returned None for pair {ctx.pair.id}"
        raise AssertionError(msg)
    return insight


async def measure_method_prescreen_cosine(ctx: LivePatrolContext) -> float:
    """Compute max method-pair cosine from live embeddings (pre-topology pre-screen)."""
    left_graph = ctx.graphs[ctx.pair.paper_a_id]
    right_graph = ctx.graphs[ctx.pair.paper_b_id]
    left_methods = method_nodes(left_graph)
    right_methods = method_nodes(right_graph)
    if not left_methods or not right_methods:
        return 0.0

    texts = [_embed_text_for_node(node) for node in left_methods + right_methods]
    vectors = await ctx.embedding_client.embed_texts(texts)
    split_at = len(left_methods)
    matrix = cosine_similarity_matrix(vectors[:split_at], vectors[split_at:])
    if matrix.size == 0:
        return 0.0
    return float(matrix.max())


def assert_primary_expectation(insight: PatrolInsight, pair: MethodOverlapGoldenPair) -> tuple[bool, str]:
    """Layer 1: deterministic status / match_type / overlap_label / theta_min."""
    return evaluate_method_overlap_golden_pair(insight, pair)


def assert_drift_guard(
    prescreen_cosine: float,
    pair: MethodOverlapGoldenPair,
    *,
    settings: Settings,
) -> tuple[bool, str]:
    """Layer 2: block semantic model right-shift on false-positive archetypes."""
    guard = pair.expectation.drift_guard
    if guard is None or not guard.enabled:
        return True, "drift_guard disabled"

    threshold = settings.patrol_semantic_threshold
    if guard.require_below_semantic_threshold and prescreen_cosine >= threshold:
        detail = (
            f"semantic drift guard tripped: prescreen_cosine={prescreen_cosine:.4f} "
            f">= PATROL_SEMANTIC_THRESHOLD={threshold}; "
            "embedding model may have shifted right — review threshold before release"
        )
        if pair.issue_id:
            detail = f"[{pair.issue_id}] {detail}"
        strict = os.environ.get(_DRIFT_GUARD_STRICT_ENV, "1").strip().lower() not in {"0", "false", "no"}
        if strict:
            return False, detail
        return True, f"WARN: {detail}"

    return True, f"prescreen_cosine={prescreen_cosine:.4f} < threshold={threshold}"


async def run_live_dual_assertion(ctx: LivePatrolContext, insight: PatrolInsight) -> LiveAssertionReport:
    """Execute both assertion layers for a completed funnel run."""
    primary_passed, primary_detail = assert_primary_expectation(insight, pair=ctx.pair)
    prescreen_cosine = await measure_method_prescreen_cosine(ctx)
    drift_passed, drift_detail = assert_drift_guard(
        prescreen_cosine,
        ctx.pair,
        settings=ctx.settings,
    )
    return LiveAssertionReport(
        primary_passed=primary_passed,
        primary_detail=primary_detail,
        prescreen_cosine=prescreen_cosine,
        drift_passed=drift_passed,
        drift_detail=drift_detail,
    )


def format_live_failure(report: LiveAssertionReport) -> str:
    """Human-readable failure message for pytest assertions."""
    parts: list[str] = []
    if not report.primary_passed:
        parts.append(f"primary: {report.primary_detail}")
    if not report.drift_passed:
        parts.append(f"drift_guard: {report.drift_detail}")
    if report.prescreen_cosine is not None:
        parts.append(f"prescreen_cosine={report.prescreen_cosine:.4f}")
    return " | ".join(parts)
