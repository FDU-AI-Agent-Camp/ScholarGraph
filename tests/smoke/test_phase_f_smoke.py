# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase F smoke: extract modules, settings, status field sanity."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from backend.agents.extract_constants import (
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.agents.extract_llm import PROMPTS_DIR, load_extract_prompt
from backend.agents.extract_types import ExtractResult
from backend.config import Settings
from backend.main import app
from backend.schemas.paper import PaperStatusData
from httpx import ASGITransport, AsyncClient

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


def _seed_isolated_hss_graph_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset services and persist hss-001 graph under an isolated GRAPH_DATA_DIR."""
    from backend.config import get_settings
    from backend.graph.store import GraphStore
    from backend.schemas.graph import UnifiedPaperGraph
    from backend.services.paper_service import get_paper_service

    graphs_dir = tmp_path / "graphs"
    graphs_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graphs_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    payload = json.loads((FIXTURES_DIR / "graph-hss.json").read_text(encoding="utf-8"))
    graph = UnifiedPaperGraph.model_validate(payload["data"]).model_copy(update={"paper_id": "hss-001"})
    GraphStore(base_dir=graphs_dir).save(graph)


def _clear_graph_env() -> None:
    from backend.config import get_settings
    from backend.services.paper_service import get_paper_service

    get_settings.cache_clear()
    get_paper_service.cache_clear()


@pytest.mark.smoke
def test_smoke_extract_prompt_files_exist() -> None:
    assert (PROMPTS_DIR / "extract_hss.md").is_file()
    assert (PROMPTS_DIR / "extract_stem.md").is_file()


@pytest.mark.smoke
def test_smoke_load_extract_prompt_returns_non_empty() -> None:
    from backend.schemas.paradigm import Paradigm

    assert len(load_extract_prompt(Paradigm.HSS).strip()) > 20
    assert len(load_extract_prompt(Paradigm.STEM).strip()) > 20


@pytest.mark.smoke
def test_smoke_extract_llm_logs_truncation() -> None:
    from backend.agents import extract_llm

    source = inspect.getsource(extract_llm.extract_with_llm)
    assert "extract_input_truncated" in source


@pytest.mark.smoke
def test_smoke_extract_settings_registered() -> None:
    settings = Settings(_env_file=None)
    assert hasattr(settings, "extract_llm_enabled")
    assert hasattr(settings, "extract_max_input_chars")
    assert hasattr(settings, "extract_heuristic_fallback")


@pytest.mark.smoke
def test_smoke_extract_warning_constants_frozen() -> None:
    assert EXTRACT_HEURISTIC_FALLBACK_CODE == "extract_heuristic_fallback"
    assert EXTRACT_HEURISTIC_FALLBACK_MESSAGE == "触发启发式Fallback!"


@pytest.mark.smoke
def test_smoke_extract_result_importable() -> None:
    assert ExtractResult.__name__ == "ExtractResult"


@pytest.mark.smoke
def test_smoke_paper_status_data_accepts_extract_warnings() -> None:
    status = PaperStatusData.model_validate(
        {
            "paper_id": "smoke-f",
            "status": "ready",
            "percent": 100,
            "stage": "ready",
            "message": "建图完成",
            "updated_at": "2026-06-07T00:00:00Z",
            "extract_warnings": [EXTRACT_HEURISTIC_FALLBACK_CODE],
        },
    )
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.smoke
def test_smoke_f22_fallback_helper_wired() -> None:
    from backend.agents import extractor

    source = inspect.getsource(extractor._fallback_to_heuristic)
    assert "extract_llm_fallback" in source
    assert "build_heuristic_graph" in source


@pytest.mark.smoke
def test_smoke_f22_heuristic_legacy_aliases_importable() -> None:
    from backend.agents import extract_heuristic

    assert callable(extract_heuristic._build_hss_graph)
    assert callable(extract_heuristic._build_stem_graph)


@pytest.mark.smoke
def test_smoke_f22_validate_llm_graph_checks_edges() -> None:
    from backend.agents.extract_llm import _validate_llm_graph

    assert "no edges" in inspect.getsource(_validate_llm_graph)


@pytest.mark.smoke
def test_smoke_f23_paper_detail_schema_has_extract_warnings() -> None:
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus

    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="smoke-f23",
        title="smoke",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        extract_warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
    )
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in detail.extract_warnings


@pytest.mark.smoke
def test_smoke_f23_fixtures_on_disk() -> None:
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
    assert (fixtures / "paper-detail-ready-fallback.json").is_file()
    assert (fixtures / "paper-status-ready-fallback.json").is_file()


@pytest.mark.smoke
def test_smoke_f23_paper_service_enrich_detail() -> None:
    from backend.services.paper_service import PaperService

    assert "_detail.assemble" in inspect.getsource(PaperService.get_paper)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_get_paper_route_includes_extract_warnings() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "extract_warnings" in data
        assert isinstance(data["extract_warnings"], list)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_status_route_includes_extract_warnings() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "extract_warnings" in data
        assert isinstance(data["extract_warnings"], list)


@pytest.mark.smoke
def test_smoke_f33_extract_hss_prompt_has_operational_definitions() -> None:
    from backend.schemas.paradigm import Paradigm

    prompt = load_extract_prompt(Paradigm.HSS)
    assert "F.3 Operational node definitions" in prompt
    assert "Thesis" in prompt
    assert "SUB_ARGUMENT_OF" in prompt
    assert "分论点支撑核心论点" in prompt
    assert "Metric" in prompt


@pytest.mark.smoke
def test_smoke_f33_extract_stem_prompt_has_operational_definitions() -> None:
    from backend.schemas.paradigm import Paradigm

    prompt = load_extract_prompt(Paradigm.STEM)
    assert "F.3 Operational node definitions" in prompt
    assert "ResearchQuestion" in prompt
    assert "ADDRESSES" in prompt
    assert "方法针对问题" in prompt
    assert "AnalyticalLens" in prompt


@pytest.mark.smoke
def test_smoke_f33_graph_hss_fixture_on_disk() -> None:
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
    assert (fixtures / "graph-hss.json").is_file()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_f33_hss_graph_endpoint_returns_thesis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_isolated_hss_graph_env(tmp_path, monkeypatch)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/papers/hss-001/graph")
        assert response.status_code == 200
        node_types = {node["type"] for node in response.json()["data"]["nodes"]}
        assert "Thesis" in node_types
        assert "SubArgument" in node_types
    finally:
        _clear_graph_env()


@pytest.mark.smoke
def test_smoke_f33_hss_prompt_forbids_metric_baseline_dataset() -> None:
    from backend.schemas.paradigm import Paradigm
    from tests.helpers.f33_hss_graphs import F33_FORBIDDEN_STEM_NODE_TYPES

    prompt = load_extract_prompt(Paradigm.HSS)
    assert "Forbidden node types" in prompt
    for stem_type in ("Metric", "Baseline", "Dataset"):
        assert stem_type in prompt
    assert {"Metric", "Baseline", "Dataset"} <= F33_FORBIDDEN_STEM_NODE_TYPES


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_f33_hss_graph_endpoint_excludes_stem_only_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.helpers.f33_hss_graphs import F33_FORBIDDEN_STEM_NODE_TYPES

    _seed_isolated_hss_graph_env(tmp_path, monkeypatch)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/papers/hss-001/graph")
        assert response.status_code == 200
        node_types = {node["type"] for node in response.json()["data"]["nodes"]}
        assert not (node_types & F33_FORBIDDEN_STEM_NODE_TYPES)
    finally:
        _clear_graph_env()


@pytest.mark.smoke
def test_smoke_f33_stem_prompt_forbids_analytical_lens_intellectual_context_object_or_data() -> None:
    from backend.schemas.paradigm import Paradigm
    from tests.helpers.f33_stem_graphs import F33_FORBIDDEN_HSS_NODE_TYPES

    prompt = load_extract_prompt(Paradigm.STEM)
    assert "Forbidden node types" in prompt
    for hss_type in ("AnalyticalLens", "IntellectualContext", "ObjectOrData"):
        assert hss_type in prompt
    assert {"AnalyticalLens", "IntellectualContext", "ObjectOrData"} <= F33_FORBIDDEN_HSS_NODE_TYPES


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_f33_stem_graph_endpoint_excludes_hss_only_types(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.config import get_settings
    from backend.graph.store import GraphStore
    from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
    from backend.schemas.paradigm import Paradigm
    from tests.helpers.f33_stem_graphs import F33_FORBIDDEN_HSS_NODE_TYPES

    graphs_dir = tmp_path / "graphs"
    graphs_dir.mkdir()
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graphs_dir))
    get_settings.cache_clear()

    GraphStore(base_dir=graphs_dir).save(
        UnifiedPaperGraph(
            paper_id="stem-001",
            paradigm=Paradigm.STEM,
            nodes=[
                GraphNode(id="n_method", label="方法", type="Method"),
                GraphNode(id="n_claim", label="声称", type="Claim"),
            ],
            edges=[
                GraphEdge(id="e1", source="n_method", target="n_claim", label="SUPPORTS", type="SUPPORTS"),
            ],
        ),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/stem-001/graph")
    assert response.status_code == 200
    node_types = {node["type"] for node in response.json()["data"]["nodes"]}
    assert not (node_types & F33_FORBIDDEN_HSS_NODE_TYPES)

    get_settings.cache_clear()
