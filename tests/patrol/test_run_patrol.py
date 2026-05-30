"""Tests for run_patrol orchestration."""

from pathlib import Path

import pytest
from backend.patrol.errors import PatrolError
from backend.patrol.service import run_patrol
from backend.schemas.patrol import PatrolMode
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


async def test_run_patrol_contradiction_success() -> None:
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis

    graphs = {
        "hss-001": build_hss_graph_with_thesis("hss-001", thesis_id="n_a", thesis_label="论点 A"),
        "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="论点 B"),
    }
    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.CONTRADICTION,
        graph_loader=graphs.get,
    )
    assert report.mode == PatrolMode.CONTRADICTION
    assert len(report.insights) == 1
    assert report.insights[0].insight_id == "ins-contradiction-001"


async def test_run_patrol_contradiction_insufficient_thesis() -> None:
    from tests.helpers.patrol_graphs import build_hss_graph_with_thesis, build_hss_graph_without_thesis

    graphs = {
        "hss-001": build_hss_graph_without_thesis("hss-001"),
        "hss-002": build_hss_graph_with_thesis("hss-002", thesis_id="n_b", thesis_label="B"),
    }
    with pytest.raises(PatrolError) as exc_info:
        await run_patrol(
            ["hss-001", "hss-002"],
            PatrolMode.CONTRADICTION,
            graph_loader=graphs.get,
        )
    assert exc_info.value.code == "PATROL_INSUFFICIENT_DATA"
