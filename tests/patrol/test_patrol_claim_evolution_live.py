"""Live regression subset for claim_evolution RQ gate (``@pytest.mark.live``).

Validates real embedding + reranker behaviour on 3 canonical golden pairs.
Excluded from default CI via pytest marker.
"""

from __future__ import annotations

import os

import pytest
from backend.config import get_settings
from backend.llm.embeddings import get_embedding_client, reset_embedding_client_cache
from backend.llm.reranker import RerankerClient
from backend.patrol.claim_evolution_rq_gate import align_research_question_pair
from backend.schemas.graph import GraphNode, NodeType
from tests.fixtures.patrol_golden_set import (
    GoldenPairExpectation,
    PatrolGoldenPair,
    load_patrol_golden_set,
)
from tests.patrol.conftest import patch_patrol_settings

pytestmark = pytest.mark.live

_LIVE_CANONICAL_PAIR_IDS = ("stem-pos-01", "stem-neg-01", "hss-neg-01")


def _live_rq_funnel_available() -> bool:
    settings = get_settings()
    if settings.is_llm_mock:
        return False
    if not settings.patrol_claim_rq_funnel_enabled():
        return False
    if settings.embedding_provider != "ollama" and not settings.embedding_api_key_effective.strip():
        return False
    return True


@pytest.fixture
def live_claim_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", os.environ.get("LLM_MODE", "live"))
    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    reset_embedding_client_cache()


@pytest.fixture
def require_live_rq_funnel(live_claim_env: None) -> None:
    if not _live_rq_funnel_available():
        pytest.skip(
            "live RQ funnel unavailable: set LLM_MODE=live, RERANKER_ENABLED=true, "
            "RERANKER_MODEL, and embedding API credentials",
        )


def _canonical_live_pairs() -> list[PatrolGoldenPair]:
    golden = load_patrol_golden_set()
    by_id = {pair.id: pair for pair in golden.pairs}
    return [by_id[pair_id] for pair_id in _LIVE_CANONICAL_PAIR_IDS]


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", _canonical_live_pairs(), ids=lambda item: item.id)
async def test_claim_evolution_golden_pair_live_rq_gate(
    pair: PatrolGoldenPair,
    require_live_rq_funnel: None,
) -> None:
    """Canonical subset must pass or fail the live two-stage RQ gate per label."""
    settings = get_settings()
    embedding_client = get_embedding_client()
    reranker_client = RerankerClient(settings)
    assert not embedding_client.is_mock

    left = GraphNode(id=f"{pair.id}-a", label=pair.label_a, type=NodeType.RESEARCH_QUESTION, data={})
    right = GraphNode(id=f"{pair.id}-b", label=pair.label_b, type=NodeType.RESEARCH_QUESTION, data={})

    aligned = await align_research_question_pair(
        [left],
        [right],
        embedding_client=embedding_client,
        settings=settings,
        reranker_client=reranker_client,
    )

    if pair.expectation == GoldenPairExpectation.POSITIVE:
        assert aligned is not None
    else:
        assert aligned is None
