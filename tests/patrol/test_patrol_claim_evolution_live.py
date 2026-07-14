"""Live regression for claim_evolution RQ gate — all 10 golden pairs (P4).

Uses ``@pytest.mark.live_patrol_logic`` and drift-tolerant score monitoring.
"""

from __future__ import annotations

import os

import pytest
from backend.config import get_settings
from backend.llm.embeddings import get_embedding_client, reset_embedding_client_cache
from backend.llm.reranker import RerankerClient
from tests.fixtures.patrol_golden_set import PatrolGoldenPair, load_patrol_golden_set
from tests.patrol.claim_evolution_live_engine import evaluate_claim_evolution_live_pair
from tests.patrol.conftest import patch_patrol_settings

pytestmark = pytest.mark.live_patrol_logic


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
    monkeypatch.setenv("RERANKER_MODEL", os.environ.get("RERANKER_MODEL", "bge-reranker-large"))
    patch_patrol_settings(
        monkeypatch,
        reranker_enabled=True,
        patrol_claim_rq_coarse_threshold=0.42,
        patrol_claim_rq_rerank_threshold=0.60,
    )
    reset_embedding_client_cache()


@pytest.fixture
async def require_live_rq_funnel(live_claim_env: None) -> None:
    if not _live_rq_funnel_available():
        pytest.skip(
            "live_patrol_logic unavailable: set LLM_MODE=live, RERANKER_ENABLED=true, "
            "RERANKER_MODEL, and embedding API credentials",
        )
    embedding_client = get_embedding_client()
    try:
        await embedding_client.embed_texts(["__live_patrol_logic_probe__"])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live_patrol_logic embedding probe failed: {exc}")


@pytest.mark.asyncio
@pytest.mark.parametrize("pair", load_patrol_golden_set().pairs, ids=lambda item: item.id)
async def test_claim_evolution_golden_pair_live_rq_gate(
    pair: PatrolGoldenPair,
    require_live_rq_funnel: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """All 10 golden pairs must pass or fail the live two-stage RQ gate per label."""
    settings = get_settings()
    embedding_client = get_embedding_client()
    reranker_client = RerankerClient(settings)
    assert not embedding_client.is_mock

    result = await evaluate_claim_evolution_live_pair(
        pair,
        embedding_client=embedding_client,
        settings=settings,
        reranker_client=reranker_client,
    )

    for warning in result.performance_warnings:
        print(f"[Performance Warning] {pair.id}: {warning}")

    assert result.status_passed, (
        f"{pair.id} live gate mismatch: expected={pair.expectation.value} "
        f"aligned={result.aligned} detail={result.detail} "
        f"live_coarse={result.live_coarse_score} live_rerank={result.live_rerank_score}"
    )

    captured = capsys.readouterr()
    if result.performance_warnings:
        assert "[Performance Warning]" in captured.out
