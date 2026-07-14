"""Integration: quality gate surfaces ready_with_warnings via HTTP API."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.extract_constants import LOW_CONFIDENCE_GRAPH_CODE
from backend.main import app
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    graph_path = tmp_path / "graphs"
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    from backend.services.paper_service import reset_persistence_singletons

    reset_persistence_singletons()
    yield graph_path
    reset_persistence_singletons()


def _make_graph(paper_id: str, *, supports_with_rationale: int, supports_without_rationale: int) -> UnifiedPaperGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    idx = 0
    for _ in range(supports_with_rationale):
        src = f"n{idx}"
        nodes.append(GraphNode(id=src, label="sub", type="SubArgument"))
        idx += 1
        tgt = f"n{idx}"
        nodes.append(GraphNode(id=tgt, label="thesis", type="Thesis"))
        idx += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src,
                target=tgt,
                label="SUPPORTS",
                type="SUPPORTS",
                rationale=f"{src} -> {tgt}",
            ),
        )
    for _ in range(supports_without_rationale):
        src = f"n{idx}"
        nodes.append(GraphNode(id=src, label="sub", type="SubArgument"))
        idx += 1
        tgt = f"n{idx}"
        nodes.append(GraphNode(id=tgt, label="thesis", type="Thesis"))
        idx += 1
        edges.append(
            GraphEdge(
                id=f"e{len(edges)}",
                source=src,
                target=tgt,
                label="SUPPORTS",
                type="SUPPORTS",
                rationale=None,
            ),
        )
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=nodes,
        edges=edges,
    )


def _seed_paper(paper_id: str) -> None:
    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="quality gate integration",
        status=PaperStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_api_ready_with_warnings_for_low_quality_graph(
    api_client: AsyncClient,
    mock_env: Path,
) -> None:
    paper_id = "quality-gate-low"
    _seed_paper(paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=1, supports_without_rationale=3)

    get_paper_service().complete_pipeline(
        paper_id,
        classification=ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test"),
        graph=graph,
    )
    from tests.helpers.event_bus_testkit import drain_event_bus

    await drain_event_bus()

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()["data"]
    assert status_data["status"] == "ready_with_warnings"
    assert status_data["stage"] == "ready"
    assert status_data["percent"] == 100
    assert LOW_CONFIDENCE_GRAPH_CODE in status_data["extract_warnings"]

    graph_resp = await api_client.get(f"/api/v1/papers/{paper_id}/graph")
    assert graph_resp.status_code == 200
    assert graph_resp.json()["data"]["paper_id"] == paper_id


@pytest.mark.asyncio
async def test_api_ready_for_high_quality_graph(
    api_client: AsyncClient,
    mock_env: Path,
) -> None:
    paper_id = "quality-gate-high"
    _seed_paper(paper_id)
    graph = _make_graph(paper_id, supports_with_rationale=3, supports_without_rationale=0)

    get_paper_service().complete_pipeline(
        paper_id,
        classification=ParadigmClassification(paradigm=Paradigm.HSS, confidence=0.9, reason="test"),
        graph=graph,
    )
    from tests.helpers.event_bus_testkit import drain_event_bus

    await drain_event_bus()

    status_resp = await api_client.get(f"/api/v1/papers/{paper_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()["data"]
    assert status_data["status"] == "ready"
    assert LOW_CONFIDENCE_GRAPH_CODE not in status_data["extract_warnings"]
