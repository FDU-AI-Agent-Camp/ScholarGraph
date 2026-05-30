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
