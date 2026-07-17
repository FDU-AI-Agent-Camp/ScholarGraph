# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Tests for run_patrol orchestration."""

from pathlib import Path

import pytest
from backend.patrol.errors import PatrolError
from backend.patrol.service import run_patrol
from backend.schemas.patrol import PatrolInsightStatus, PatrolMode
from tests.helpers.patrol_graphs import build_hss_graph_with_lens, seed_patrol_graphs


async def test_run_patrol_lens_clash_success(tmp_path: Path) -> None:
    store_dir = tmp_path / "graphs"
    seed_patrol_graphs(
        store_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    from backend.graph.store import GraphStore

    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.LENS_CLASH,
        store=GraphStore(base_dir=store_dir),
    )
    assert report.mode == PatrolMode.LENS_CLASH
    assert report.paper_ids == ["hss-001", "hss-002"]
    assert len(report.insights) == 1
    assert report.generated_at is not None


async def test_run_patrol_rejects_single_paper() -> None:
    with pytest.raises(PatrolError) as exc_info:
        await run_patrol(["hss-001"], PatrolMode.LENS_CLASH)
    assert exc_info.value.code == "PATROL_INVALID_REQUEST"
    assert exc_info.value.status_code == 400


async def test_run_patrol_rejects_three_papers() -> None:
    with pytest.raises(PatrolError) as exc_info:
        await run_patrol(["hss-001", "hss-002", "hss-003"], PatrolMode.LENS_CLASH)
    assert exc_info.value.code == "PATROL_INVALID_REQUEST"


async def test_run_patrol_raises_when_graph_missing(tmp_path: Path) -> None:
    from backend.graph.store import GraphStore

    with pytest.raises(PatrolError) as exc_info:
        await run_patrol(
            ["hss-001", "hss-002"],
            PatrolMode.LENS_CLASH,
            store=GraphStore(base_dir=tmp_path / "empty"),
        )
    assert exc_info.value.code == "GRAPH_NOT_READY"
    assert exc_info.value.status_code == 409


async def test_run_patrol_insufficient_lens_data() -> None:
    from tests.helpers.patrol_graphs import build_hss_graph_without_lens

    graphs = {
        "hss-001": build_hss_graph_without_lens("hss-001"),
        "hss-002": build_hss_graph_with_lens("hss-002", lens_id="n_b", lens_label="B"),
    }
    with pytest.raises(PatrolError) as exc_info:
        await run_patrol(
            ["hss-001", "hss-002"],
            PatrolMode.LENS_CLASH,
            graph_loader=graphs.get,
        )
    assert exc_info.value.code == "PATROL_INSUFFICIENT_DATA"
    assert exc_info.value.status_code == 422


async def test_run_patrol_insight_matches_openapi_fields(tmp_path: Path) -> None:
    store_dir = tmp_path / "graphs"
    seed_patrol_graphs(
        store_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    from backend.graph.store import GraphStore

    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.LENS_CLASH,
        store=GraphStore(base_dir=store_dir),
    )
    payload = report.model_dump(mode="json")
    assert payload["mode"] == "lens_clash"
    assert set(payload["insights"][0]["node_refs"][0]) == {"paper_id", "node_id", "label"}


# ------------------------------------------------------------------
# Red-bar tests: verify the new schema/modes exist before implementation.
# ------------------------------------------------------------------


def test_method_overlap_mode_exists_in_patrol_mode_enum() -> None:
    assert hasattr(PatrolMode, "METHOD_OVERLAP")
    assert PatrolMode.METHOD_OVERLAP.value == "method_overlap"


def test_claim_evolution_mode_exists_in_patrol_mode_enum() -> None:
    assert hasattr(PatrolMode, "CLAIM_EVOLUTION")
    assert PatrolMode.CLAIM_EVOLUTION.value == "claim_evolution"


def test_structured_points_field_exists_on_patrol_insight() -> None:
    from backend.schemas.patrol import PatrolInsight

    fields = PatrolInsight.model_fields
    assert "structured_points" in fields


# ------------------------------------------------------------------
# Integration tests for new patrol modes.
# ------------------------------------------------------------------


async def test_run_patrol_method_overlap_success(tmp_path: Path) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset

    store_dir = tmp_path / "graphs"
    store = GraphStore(base_dir=store_dir)
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
    report = await run_patrol(
        ["stem-001", "stem-002"],
        PatrolMode.METHOD_OVERLAP,
        store=store,
    )
    assert report.mode == PatrolMode.METHOD_OVERLAP
    assert len(report.insights) == 1
    assert report.insights[0].insight_id == "ins-method-overlap-001"
    assert len(report.insights[0].structured_points) == 1


async def test_run_patrol_claim_evolution_success(tmp_path: Path) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_question_claim

    store_dir = tmp_path / "graphs"
    store = GraphStore(base_dir=store_dir)
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
    report = await run_patrol(
        ["stem-001", "stem-002"],
        PatrolMode.CLAIM_EVOLUTION,
        store=store,
    )
    assert report.mode == PatrolMode.CLAIM_EVOLUTION
    assert len(report.insights) == 1
    assert report.insights[0].insight_id == "ins-claim-evolution-001"
    assert len(report.insights[0].structured_points) == 1


async def test_run_patrol_mixed_context_calls_vector_store(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock

    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset

    store_dir = tmp_path / "graphs"
    store = GraphStore(base_dir=store_dir)
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
    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = []
    await run_patrol(
        ["stem-001", "stem-002"],
        PatrolMode.METHOD_OVERLAP,
        store=store,
        vector_store=vector_store,
    )
    assert vector_store.query_chunks.await_count == 2


async def test_run_patrol_gracefully_degrades_without_vector_store(tmp_path: Path) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_stem_graph_with_method_dataset

    store_dir = tmp_path / "graphs"
    store = GraphStore(base_dir=store_dir)
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
    report = await run_patrol(
        ["stem-001", "stem-002"],
        PatrolMode.METHOD_OVERLAP,
        store=store,
    )
    assert report.mode == PatrolMode.METHOD_OVERLAP
    assert len(report.insights) == 1


async def test_run_patrol_contradiction_uses_vector_store() -> None:
    """Orchestration must pass vector_store into build_contradiction_insight."""
    from unittest.mock import AsyncMock

    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis

    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_a",
            thesis_label="论点 A",
            sub_arguments=[("n_sub_a", "分论点 A")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_b",
            thesis_label="论点 B",
            sub_arguments=[("n_sub_b", "分论点 B")],
        ),
    }
    vector_store = AsyncMock()
    vector_store.query_chunks.return_value = []
    vector_store.exists.return_value = True
    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.CONTRADICTION,
        graph_loader=graphs.get,
        vector_store=vector_store,
    )
    assert report.mode == PatrolMode.CONTRADICTION
    assert len(report.insights) == 1
    # vector_store should be queried for RAG context enrichment using the thesis label.
    vector_store.query_chunks.assert_any_await("论点 A 引言 结论 核心论点 论证", paper_id="hss-001", top_k=3)
    vector_store.query_chunks.assert_any_await("论点 B 引言 结论 核心论点 论证", paper_id="hss-002", top_k=3)
    # No degradation flag because exists() returned True.
    assert report.insights[0].is_degraded is False
    assert report.insights[0].degradation_profile is None
    assert "patrol_rag_context_degraded" not in report.insights[0].meta


async def test_run_patrol_contradiction_success() -> None:
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis

    graphs = {
        "hss-001": build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_a",
            thesis_label="论点 A",
            sub_arguments=[("n_sub_a", "分论点 A")],
        ),
        "hss-002": build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_b",
            thesis_label="论点 B",
            sub_arguments=[("n_sub_b", "分论点 B")],
        ),
    }
    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.CONTRADICTION,
        graph_loader=graphs.get,
    )
    assert report.mode == PatrolMode.CONTRADICTION
    assert len(report.insights) == 1
    assert report.insights[0].insight_id == "ins-contradiction-001"
    assert report.insights[0].status == PatrolInsightStatus.READY


async def test_run_patrol_contradiction_insufficient_thesis() -> None:
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis, build_hss_graph_without_thesis

    graphs = {
        "hss-001": build_hss_graph_without_thesis("hss-001"),
        "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="B"),
    }
    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.CONTRADICTION,
        graph_loader=graphs.get,
    )
    assert report.mode == PatrolMode.CONTRADICTION
    assert len(report.insights) == 1
    assert report.insights[0].status == PatrolInsightStatus.INSUFFICIENT_DATA
    assert report.insights[0].has_contradiction is False
