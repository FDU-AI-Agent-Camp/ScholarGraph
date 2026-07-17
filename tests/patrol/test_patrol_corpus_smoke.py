# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Corpus-aligned patrol smoke (handoff §5: 2× HSS → ≥1 Lens Clash insight)."""

from backend.graph.store import GraphStore
from backend.patrol.service import run_patrol
from backend.schemas.patrol import PatrolMode
from tests.helpers.patrol_samples import CORPUS_HSS_PAPER_IDS, CORPUS_PATROL_LENSES, seed_corpus_patrol_graphs


async def test_corpus_hss_pair_produces_lens_clash_insight(patrol_graph_dir) -> None:
    seed_corpus_patrol_graphs(patrol_graph_dir)
    report = await run_patrol(
        list(CORPUS_HSS_PAPER_IDS),
        PatrolMode.LENS_CLASH,
        store=GraphStore(base_dir=patrol_graph_dir),
    )
    assert report.mode == PatrolMode.LENS_CLASH
    assert report.paper_ids == list(CORPUS_HSS_PAPER_IDS)
    assert len(report.insights) >= 1
    insight = report.insights[0]
    assert insight.title
    assert len(insight.node_refs) == 2
    labels = {ref.label for ref in insight.node_refs}
    expected = {labels_pair[1] for labels_pair in CORPUS_PATROL_LENSES.values()}
    assert labels == expected
    assert CORPUS_PATROL_LENSES["hss-001"][1] in insight.summary
    assert CORPUS_PATROL_LENSES["hss-002"][1] in insight.summary


async def test_corpus_hss_pair_produces_contradiction_insight(patrol_graph_dir) -> None:
    from backend.graph.store import GraphStore
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis

    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(
        build_hss_graph_with_thesis(
            "hss-001",
            thesis_id="n_t_a",
            thesis_label="夏尔巴父系源流具有多元融合特征",
        ),
    )
    store.save(
        build_hss_graph_with_thesis(
            "hss-002",
            thesis_id="n_t_b",
            thesis_label="电影政治传播强化主流意识形态建构",
        ),
    )
    report = await run_patrol(
        list(CORPUS_HSS_PAPER_IDS),
        PatrolMode.CONTRADICTION,
        store=store,
    )
    assert report.mode == PatrolMode.CONTRADICTION
    assert len(report.insights) >= 1
    assert report.insights[0].insight_id == "ins-contradiction-001"
    assert len(report.insights[0].node_refs) == 2


async def test_corpus_stem_pair_produces_method_overlap_insight(patrol_graph_dir) -> None:
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
    report = await run_patrol(
        ["stem-001", "stem-002"],
        PatrolMode.METHOD_OVERLAP,
        store=store,
    )
    assert report.mode == PatrolMode.METHOD_OVERLAP
    assert len(report.insights) >= 1
    assert report.insights[0].insight_id == "ins-method-overlap-001"


async def test_corpus_stem_pair_produces_claim_evolution_insight(patrol_graph_dir) -> None:
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
    report = await run_patrol(
        ["stem-001", "stem-002"],
        PatrolMode.CLAIM_EVOLUTION,
        store=store,
    )
    assert report.mode == PatrolMode.CLAIM_EVOLUTION
    assert len(report.insights) >= 1
    assert report.insights[0].insight_id == "ins-claim-evolution-001"
