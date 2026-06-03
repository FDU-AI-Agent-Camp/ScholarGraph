"""PatrolService integration with real run_patrol (no mocks)."""

import pytest
from backend.api.exceptions import ApiError
from backend.graph.store import GraphStore
from backend.schemas.patrol import PatrolMode
from backend.services.patrol_service import PatrolService, get_patrol_service
from tests.helpers.patrol_graphs import (
    build_hss_graph_with_lens,
    build_hss_graph_with_thesis,
    build_hss_graph_without_lens,
    build_hss_graph_without_thesis,
)
from tests.helpers.patrol_samples import CORPUS_HSS_PAPER_IDS, seed_corpus_patrol_graphs


async def test_patrol_service_runs_real_lens_clash(patrol_graph_dir) -> None:
    seed_corpus_patrol_graphs(patrol_graph_dir)
    service = PatrolService(store=GraphStore(base_dir=patrol_graph_dir))
    report = await service.run_patrol(list(CORPUS_HSS_PAPER_IDS), PatrolMode.LENS_CLASH)
    assert len(report.insights) >= 1
    assert report.insights[0].node_refs


async def test_patrol_service_passes_injected_store(patrol_graph_dir) -> None:
    seed_corpus_patrol_graphs(patrol_graph_dir)
    service = PatrolService(store=GraphStore(base_dir=patrol_graph_dir))
    report = await service.run_patrol(["hss-001", "hss-002"], PatrolMode.LENS_CLASH)
    assert report.paper_ids == ["hss-001", "hss-002"]


async def test_patrol_service_maps_graph_not_ready_to_api_error(patrol_graph_dir) -> None:
    service = PatrolService(store=GraphStore(base_dir=patrol_graph_dir))
    with pytest.raises(ApiError) as exc_info:
        await service.run_patrol(list(CORPUS_HSS_PAPER_IDS), PatrolMode.LENS_CLASH)
    assert exc_info.value.code == "GRAPH_NOT_READY"
    assert exc_info.value.status_code == 409


async def test_patrol_service_maps_insufficient_lens_data_to_api_error(patrol_graph_dir) -> None:
    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_without_lens("hss-001"))
    store.save(build_hss_graph_with_lens("hss-002", lens_id="n_b", lens_label="B"))
    service = PatrolService(store=store)
    with pytest.raises(ApiError) as exc_info:
        await service.run_patrol(["hss-001", "hss-002"], PatrolMode.LENS_CLASH)
    assert exc_info.value.code == "PATROL_INSUFFICIENT_DATA"
    assert exc_info.value.status_code == 422


def test_get_patrol_service_returns_singleton() -> None:
    get_patrol_service.cache_clear()
    try:
        first = get_patrol_service()
        second = get_patrol_service()
        assert first is second
    finally:
        get_patrol_service.cache_clear()


async def test_patrol_service_runs_contradiction_mode(patrol_graph_dir) -> None:
    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_with_thesis("hss-001", thesis_id="n_a", thesis_label="论点 A"))
    store.save(build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="论点 B"))
    service = PatrolService(store=store)
    report = await service.run_patrol(["hss-001", "hss-002"], PatrolMode.CONTRADICTION)
    assert report.mode == PatrolMode.CONTRADICTION
    assert report.insights[0].insight_id == "ins-contradiction-001"


async def test_patrol_service_maps_contradiction_insufficient_data(patrol_graph_dir) -> None:
    store = GraphStore(base_dir=patrol_graph_dir)
    store.save(build_hss_graph_without_thesis("hss-001"))
    store.save(build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="B"))
    service = PatrolService(store=store)
    with pytest.raises(ApiError) as exc_info:
        await service.run_patrol(["hss-001", "hss-002"], PatrolMode.CONTRADICTION)
    assert exc_info.value.code == "PATROL_INSUFFICIENT_DATA"
    assert exc_info.value.status_code == 422
