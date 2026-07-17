# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Track B — demo profile admission tests (``@pytest.mark.demo_profile_check``).

Unlike Track A mock CI (``GoldenPairRerankerClient`` injected scores), this track
exercises the full claim_evolution funnel with real embedding + reranker clients
when ``APP_PROFILE=demo`` and ``RERANKER_ENABLED=true``.

Run locally or on staging::

    uv run pytest -m demo_profile_check
"""

from __future__ import annotations

import os

import pytest
from backend.api.health_telemetry import build_patrol_service_health
from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.llm.embeddings import get_embedding_client, reset_embedding_client_cache
from backend.llm.reranker import RerankerClient
from backend.patrol.claim_evolution import build_claim_evolution_insight
from backend.schemas.patrol import ClaimEvolutionPoint, PatrolInsightStatus, PatrolMode
from backend.services.patrol_service import PatrolService
from tests.fixtures.demo_profile_check import demo_profile_check_available, demo_profile_skip_reason
from tests.helpers.patrol_graphs import build_stem_graph_with_question_claim
from tests.patrol.conftest import patch_patrol_settings, reset_patrol_runtime_caches

pytestmark = pytest.mark.demo_profile_check

_DEMO_RQ_LABEL = "PCA 是否提升分类准确率？"
_DEMO_CLAIM_A = "准确率提升 5%"
_DEMO_CLAIM_B = "准确率无显著变化"


def _assert_claim_evolution_topology(point: ClaimEvolutionPoint) -> None:
    assert point.mode == "claim_evolution"
    assert point.research_question.strip()
    assert point.paper_a_claim and point.paper_a_claim.strip()
    assert point.paper_b_claim and point.paper_b_claim.strip()


@pytest.fixture
def demo_profile_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate staging/demo topology without loading repository ``.env.demo``."""
    monkeypatch.setenv("APP_PROFILE", "demo")
    monkeypatch.setenv("LLM_MODE", os.environ.get("LLM_MODE", "live"))
    monkeypatch.setenv("STARTUP_RERANKER_PROBE", "false")
    monkeypatch.setenv("RERANKER_MODEL", "bge-reranker-large")
    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    reset_patrol_runtime_caches()
    reset_embedding_client_cache()


@pytest.fixture
async def require_demo_profile_live(demo_profile_env: None) -> None:
    if not demo_profile_check_available():
        pytest.skip(demo_profile_skip_reason())
    embedding_client = get_embedding_client()
    try:
        await embedding_client.embed_texts(["__demo_profile_probe__"])
    except Exception as exc:  # noqa: BLE001 — admission gate skips when live APIs are unreachable
        pytest.skip(f"demo_profile_check embedding probe failed: {exc}")


def test_demo_profile_health_reports_ready_reranker(demo_profile_env: None) -> None:
    settings = get_settings()
    assert settings.app_profile == "demo"
    patrol = build_patrol_service_health(settings)
    assert patrol["claim_rq_funnel_enabled"] is True
    assert patrol["reranker_status"] == "READY"
    assert patrol["status"] == "fully_functional"


@pytest.mark.asyncio
async def test_demo_profile_claim_evolution_structured_points_topology(
    require_demo_profile_live: None,
) -> None:
    """Full funnel (no mock rerank scores) must emit READY + structured_points."""
    settings = get_settings()
    embedding_client = get_embedding_client()
    reranker_client = RerankerClient(settings)
    assert not embedding_client.is_mock
    assert settings.reranker_enabled is True

    graphs = {
        "stem-001": build_stem_graph_with_question_claim(
            "stem-001",
            question_label=_DEMO_RQ_LABEL,
            claim_label=_DEMO_CLAIM_A,
        ),
        "stem-002": build_stem_graph_with_question_claim(
            "stem-002",
            question_label=_DEMO_RQ_LABEL,
            claim_label=_DEMO_CLAIM_B,
        ),
    }

    insight = await build_claim_evolution_insight(
        graphs,
        ["stem-001", "stem-002"],
        embedding_client=embedding_client,
        reranker_client=reranker_client,
    )
    assert insight is not None
    assert insight.status == PatrolInsightStatus.READY
    assert len(insight.structured_points) == 1
    point = insight.structured_points[0]
    assert isinstance(point, ClaimEvolutionPoint)
    _assert_claim_evolution_topology(point)
    assert insight.node_refs


@pytest.mark.asyncio
async def test_demo_profile_patrol_service_claim_evolution_e2e(
    patrol_graph_dir,
    require_demo_profile_live: None,
) -> None:
    """PatrolService end-to-end under demo profile without injected mock scores."""
    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(
        build_stem_graph_with_question_claim(
            "stem-001",
            question_label=_DEMO_RQ_LABEL,
            claim_label=_DEMO_CLAIM_A,
        ),
    )
    store.save(
        build_stem_graph_with_question_claim(
            "stem-002",
            question_label=_DEMO_RQ_LABEL,
            claim_label=_DEMO_CLAIM_B,
        ),
    )
    service = PatrolService(store=store)
    report = await service.run_patrol(["stem-001", "stem-002"], PatrolMode.CLAIM_EVOLUTION)

    assert report.mode == PatrolMode.CLAIM_EVOLUTION
    assert report.insights[0].status == PatrolInsightStatus.READY
    assert report.insights[0].structured_points[0].mode == "claim_evolution"
    _assert_claim_evolution_topology(report.insights[0].structured_points[0])  # type: ignore[arg-type]
