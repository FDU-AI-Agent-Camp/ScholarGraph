"""HTTP integration tests for POST /api/v1/patrol."""

import pytest
from backend.schemas.patrol_llm import ClaimEvolutionOutput, MethodOverlapOutput
from httpx import AsyncClient
from tests.helpers.patrol_graphs import (
    build_hss_graph_without_lens,
    seed_patrol_graphs,
)
from tests.patrol.conftest import assert_api_envelope


@pytest.mark.asyncio
async def test_patrol_api_lens_clash_success(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    seed_patrol_graphs(
        patrol_graph_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 200
    body = response.json()
    assert_api_envelope(body)
    data = body["data"]
    assert data["mode"] == "lens_clash"
    assert data["paper_ids"] == ["hss-001", "hss-002"]
    assert len(data["insights"]) == 1
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-lens-clash-001"
    assert len(insight["node_refs"]) == 2
    assert insight["node_refs"][0]["label"] == "消费社会"
    assert data["generated_at"]


@pytest.mark.asyncio
async def test_patrol_api_defaults_mode_to_lens_clash(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    seed_patrol_graphs(
        patrol_graph_dir,
        {
            "hss-001": ("n_lens_a", "历史制度主义"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["mode"] == "lens_clash"


@pytest.mark.asyncio
async def test_patrol_api_rejects_single_paper_id(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001"], "mode": "lens_clash"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patrol_api_rejects_three_paper_ids(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002", "hss-003"], "mode": "lens_clash"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patrol_api_graph_not_ready_returns_409(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    _ = patrol_graph_dir
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "GRAPH_NOT_READY"


@pytest.mark.asyncio
async def test_patrol_api_insufficient_lens_data_returns_422(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_hss_graph_with_lens

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_without_lens("hss-001"))
    store.save(build_hss_graph_with_lens("hss-002", lens_id="n_lens_b", lens_label="公共领域"))

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PATROL_INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_patrol_api_service_integration_matches_corpus_smoke(
    api_client,
    patrol_graph_dir,
) -> None:
    """POST /patrol uses PatrolService → real run_patrol (handoff §5)."""
    from tests.helpers.patrol_samples import CORPUS_HSS_PAPER_IDS, seed_corpus_patrol_graphs

    seed_corpus_patrol_graphs(patrol_graph_dir)
    response = await api_client.post(
        "/api/v1/patrol",
        json={
            "paper_ids": list(CORPUS_HSS_PAPER_IDS),
            "mode": "lens_clash",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["insights"]) >= 1
    assert data["insights"][0]["node_refs"]


@pytest.mark.asyncio
async def test_patrol_api_contradiction_mode_success(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(
        build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_t_a",
            thesis_label="夏尔巴父系源流具有多元融合特征",
            sub_arguments=[("n_sub_a", "分论点：分子证据支持混合来源")],
        ),
    )
    store.save(
        build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_t_b",
            thesis_label="电影政治传播强化主流意识形态建构",
            sub_arguments=[("n_sub_b", "分论点：叙事策略随政策周期变化")],
        ),
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "contradiction"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "contradiction"
    assert len(data["insights"]) >= 1
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-contradiction-001"
    assert insight["status"] == "ready"


@pytest.mark.asyncio
async def test_patrol_api_contradiction_insufficient_data_returns_200(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis, build_hss_graph_without_thesis

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_without_thesis("hss-001"))
    store.save(build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="B"))
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "contradiction"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "contradiction"
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-contradiction-001"
    assert insight["status"] == "insufficient_data"
    assert insight["has_contradiction"] is False


@pytest.mark.asyncio
async def test_patrol_api_contradiction_both_papers_lack_subarguments_returns_insufficient_data(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_with_thesis("hss-001", thesis_id="n_a", thesis_label="论点 A"))
    store.save(build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="论点 B"))
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "contradiction"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    insight = data["insights"][0]
    assert insight["status"] == "insufficient_data"
    assert "hss-001" in insight["summary"]
    assert "hss-002" in insight["summary"]


@pytest.mark.asyncio
async def test_api_patrol_rejects_unsupported_mode_before_graph_load(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "unsupported_mode"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_method_overlap_e2e_contract(
    api_client: AsyncClient,
    patrol_graph_dir,
    monkeypatch,
) -> None:
    """E2E contract test: method_overlap returns LLM-aligned structured points without placeholders."""
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset

    llm_output = {
        "summary": "两篇论文均使用 PCA 对图像特征进行降维处理。",
        "comparison_details": [
            {
                "method_pair_name": "PCA <-> PCA",
                "paper_a_usage": "论文 A 在 MNIST 上使用 PCA 保留 95% 方差进行降维。",
                "paper_b_usage": "论文 B 在 CIFAR-10 上使用 PCA 保留 90% 方差进行降维。",
                "evidence_summary": "两者都利用 PCA 降低输入维度，但论文 B 的数据集更复杂。",
            },
        ],
    }

    async def _mock_method_overlap_summary(context: str, *, llm_client=None) -> MethodOverlapOutput:
        return MethodOverlapOutput.model_validate(llm_output)

    monkeypatch.setattr(
        "backend.patrol.method_overlap.generate_method_overlap_summary",
        _mock_method_overlap_summary,
    )

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(
        build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="MNIST",
        ),
    )
    store.save(
        build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="CIFAR-10",
        ),
    )

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
    )
    assert response.status_code == 200
    body = response.json()
    assert_api_envelope(body)
    data = body["data"]
    assert data["mode"] == "method_overlap"
    assert len(data["insights"]) == 1
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-method-overlap-001"
    assert insight["status"] == "ready"
    assert insight["summary"] == llm_output["summary"]

    points = insight["structured_points"]
    assert len(points) == 1
    point = points[0]
    assert point["mode"] == "method_overlap"
    assert point["overlap_type"] == "method"
    assert point["overlap_label"] == "PCA"
    assert point["method"] == "PCA"  # backwards-compatible alias
    assert point["overlap_score"] == 1.0
    assert point["match_type"] == "literal"
    assert point["paper_a_usage"] == llm_output["comparison_details"][0]["paper_a_usage"]
    assert point["paper_b_usage"] == llm_output["comparison_details"][0]["paper_b_usage"]
    assert point["evidence_summary"] == llm_output["comparison_details"][0]["evidence_summary"]
    assert "用于" not in point["paper_a_usage"]
    assert "用于" not in point["paper_b_usage"]
    assert "placeholder" not in (point["paper_a_usage"] + point["paper_b_usage"]).lower()


@pytest.mark.asyncio
async def test_api_claim_evolution_e2e_contract(
    api_client: AsyncClient,
    patrol_graph_dir,
    monkeypatch,
) -> None:
    """E2E contract test: claim_evolution returns strong-typed evolution_type without placeholders."""
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_question_claim

    llm_output = {
        "evolution_type": "contradict",
        "problem_fit_score": 88,
        "comparison_summary": "两篇论文对 PCA 效果的结论存在分歧。",
        "evidence_summary": "论文 A 认为准确率提升，论文 B 认为无显著变化。",
    }

    async def _mock_claim_evolution_summary(context: str, *, llm_client=None) -> ClaimEvolutionOutput:
        return ClaimEvolutionOutput.model_validate(llm_output)

    monkeypatch.setattr(
        "backend.patrol.claim_evolution.generate_claim_evolution_summary",
        _mock_claim_evolution_summary,
    )

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(
        build_stem_graph_with_question_claim(
            "stem-001",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
    )
    store.save(
        build_stem_graph_with_question_claim(
            "stem-002",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率无显著变化",
        ),
    )

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "claim_evolution"},
    )
    assert response.status_code == 200
    body = response.json()
    assert_api_envelope(body)
    data = body["data"]
    assert data["mode"] == "claim_evolution"
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-claim-evolution-001"
    assert insight["status"] == "ready"
    assert insight["summary"] == llm_output["comparison_summary"]

    points = insight["structured_points"]
    assert len(points) == 1
    point = points[0]
    assert point["mode"] == "claim_evolution"
    assert point["evolution_type"] == "contradict"
    assert point["problem_fit_score"] == 88
    assert point["paper_a_claim"] == "准确率提升 5%"
    assert point["paper_b_claim"] == "准确率无显著变化"
    assert point["evidence_summary"] == llm_output["evidence_summary"]
    assert "未检出明确结论" not in (point["evidence_summary"] or "")


@pytest.mark.asyncio
async def test_api_method_overlap_returns_structured_points(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(
        build_stem_graph_with_method_dataset(
            "stem-001",
            method_label="PCA",
            dataset_label="Dataset A",
        ),
    )
    store.save(
        build_stem_graph_with_method_dataset(
            "stem-002",
            method_label="PCA",
            dataset_label="Dataset B",
        ),
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
    )
    assert response.status_code == 200
    body = response.json()
    assert_api_envelope(body)
    data = body["data"]
    assert data["mode"] == "method_overlap"
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-method-overlap-001"
    assert len(insight["structured_points"]) == 1
    assert insight["structured_points"][0]["mode"] == "method_overlap"


@pytest.mark.asyncio
async def test_api_method_overlap_insufficient_data_returns_200(
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
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "method_overlap"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "method_overlap"
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-method-overlap-001"
    assert insight["status"] == "insufficient_data"
    assert insight["structured_points"] == []


@pytest.mark.asyncio
async def test_api_claim_evolution_returns_structured_points(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_question_claim

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(
        build_stem_graph_with_question_claim(
            "stem-001",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率提升 5%",
        ),
    )
    store.save(
        build_stem_graph_with_question_claim(
            "stem-002",
            question_label="PCA 是否提升分类准确率？",
            claim_label="准确率无显著变化",
        ),
    )
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "claim_evolution"},
    )
    assert response.status_code == 200
    body = response.json()
    assert_api_envelope(body)
    data = body["data"]
    assert data["mode"] == "claim_evolution"
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-claim-evolution-001"
    assert len(insight["structured_points"]) == 1
    assert insight["structured_points"][0]["mode"] == "claim_evolution"


@pytest.mark.asyncio
async def test_api_claim_evolution_insufficient_data_returns_200(
    api_client: AsyncClient,
    patrol_graph_dir,
) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_stem_graph_with_method_dataset("stem-001", method_label="PCA", dataset_label="D1"))
    store.save(build_stem_graph_with_method_dataset("stem-002", method_label="Random Forest", dataset_label="D2"))
    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["stem-001", "stem-002"], "mode": "claim_evolution"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "claim_evolution"
    insight = data["insights"][0]
    assert insight["insight_id"] == "ins-claim-evolution-001"
    assert insight["status"] == "insufficient_data"
    assert insight["structured_points"] == []
