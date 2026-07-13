"""Live regression for method_overlap golden pairs (``@pytest.mark.live``).

Requires live embedding credentials (``LLM_MODE=live`` + embedding API key).
Excluded from default CI via pytest marker.
"""

from __future__ import annotations

import os

import pytest
from backend.config import get_settings
from backend.llm.embeddings import get_embedding_client, reset_embedding_client_cache
from backend.patrol.method_overlap import build_method_overlap_insight
from backend.schemas.patrol import PatrolInsightStatus
from tests.fixtures.patrol_method_overlap_golden import (
    MethodOverlapGoldenExpectation,
    MethodOverlapGoldenPair,
    build_graphs_for_pair,
    golden_set_path,
    load_method_overlap_golden_set,
)
from tests.patrol.conftest import patch_patrol_settings

pytestmark = pytest.mark.live


def _live_embedding_available() -> bool:
    settings = get_settings()
    if settings.is_llm_mock:
        return False
    if settings.embedding_provider == "ollama":
        return True
    key = settings.embedding_api_key_effective
    return bool(key and key.strip())


@pytest.fixture
def live_patrol_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt out of patrol conftest mock isolation for live embedding runs."""
    monkeypatch.setenv("LLM_MODE", os.environ.get("LLM_MODE", "live"))
    if not os.environ.get("SCHOLARGRAPH_API_KEY") and os.environ.get("EMBEDDING_API_KEY"):
        monkeypatch.setenv("SCHOLARGRAPH_API_KEY", os.environ["EMBEDDING_API_KEY"])
    patch_patrol_settings(monkeypatch, enable_patrol_semantic_path=True)
    reset_embedding_client_cache()


@pytest.fixture
def require_live_embedding(live_patrol_env: None) -> None:
    if not _live_embedding_available():
        pytest.skip("live embedding unavailable: set LLM_MODE=live and embedding API credentials")


def test_method_overlap_golden_set_file_exists_and_validates() -> None:
    assert golden_set_path().is_file()
    golden = load_method_overlap_golden_set()
    assert golden.dataset_id == "patrol-method-overlap-golden"
    assert len(golden.pairs) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pair",
    load_method_overlap_golden_set().pairs,
    ids=lambda item: item.id,
)
async def test_method_overlap_golden_pair_live_expectation(
    pair: MethodOverlapGoldenPair,
    require_live_embedding: None,
) -> None:
    """Each golden pair must pass or fail method_overlap per its label (live embeddings)."""
    graphs = build_graphs_for_pair(pair)
    paper_ids = [pair.paper_a_id, pair.paper_b_id]
    embedding_client = get_embedding_client()
    assert not embedding_client.is_mock

    insight = await build_method_overlap_insight(
        graphs,
        paper_ids,
        embedding_client=embedding_client,
    )
    assert insight is not None

    if pair.expectation == MethodOverlapGoldenExpectation.POSITIVE:
        assert insight.status == PatrolInsightStatus.READY
        assert len(insight.structured_points) >= 1
    else:
        assert insight.status == PatrolInsightStatus.INSUFFICIENT_DATA
        assert insight.structured_points == []
