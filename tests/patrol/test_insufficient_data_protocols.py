"""P11: channel-A (422) vs channel-B (200 + insufficient_data + exclusion_logic)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_channel_a_lens_clash_missing_lens_returns_422(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_question_claim

    store = GraphStore(base_dir=patrol_graph_dir)
    # STEM graphs without AnalyticalLens — hard preflight barrier for lens_clash.
    store.save(build_stem_graph_with_question_claim("stem-001", question_label="Q1", claim_label="C1"))
    store.save(build_stem_graph_with_question_claim("stem-002", question_label="Q2", claim_label="C2"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "PATROL_INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_channel_b_method_overlap_hss_returns_200_with_exclusion_logic(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_hss_graph_with_lens

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_with_lens("hss-001", lens_id="n_lens_a", lens_label="消费社会"))
    store.save(build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label="公共领域"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "method_overlap"},
    )
    assert response.status_code == 200
    insight = response.json()["data"]["insights"][0]
    assert insight["status"] == "insufficient_data"
    logic = insight["exclusion_logic"]
    assert logic is not None
    assert logic["reason_code"] == "PARADIGM_UNSUPPORTED"
    assert logic["phase"] == "PARADIGM_GATE"
    assert isinstance(logic["description"], str) and logic["description"].strip()
    assert logic["metrics"]["required_paradigm"] == "STEM"


@pytest.mark.asyncio
async def test_channel_b_contradiction_missing_thesis_returns_exclusion_logic(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_question_claim

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_stem_graph_with_question_claim("stem-001", question_label="Q1", claim_label="C1"))
    store.save(build_stem_graph_with_question_claim("stem-002", question_label="Q2", claim_label="C2"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "contradiction"},
    )
    assert response.status_code == 200
    insight = response.json()["data"]["insights"][0]
    assert insight["status"] == "insufficient_data"
    logic = insight["exclusion_logic"]
    assert logic["reason_code"] == "MISSING_REQUIRED_NODES"
    assert logic["phase"] == "NODE_PRECHECK"
    assert logic["metrics"]["missing_node_type"] == "Thesis"


def test_patrol_insight_rejects_insufficient_data_without_exclusion_logic() -> None:
    from backend.schemas.patrol import PatrolInsight, PatrolInsightStatus
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="exclusion_logic"):
        PatrolInsight(
            insight_id="ins-bad",
            title="t",
            summary="s",
            status=PatrolInsightStatus.INSUFFICIENT_DATA,
            paper_ids=["a", "b"],
        )
