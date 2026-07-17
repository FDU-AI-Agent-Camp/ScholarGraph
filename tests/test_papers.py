# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Paper API smoke tests."""

from pathlib import Path

import pytest
from backend.main import app
from httpx import ASGITransport, AsyncClient

from tests.helpers.persistence_testkit import init_isolated_database, reset_persistence_singletons


@pytest.mark.asyncio
async def test_list_papers_returns_fixture_seed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.services.paper_service import get_paper_service

    db_path = tmp_path / "scholargraph.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SEED_DEMO_PAPERS", "true")
    reset_persistence_singletons()
    await init_isolated_database(db_path)
    await get_paper_service().bootstrap()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["total"] >= 1
    assert len(body["data"]["items"]) >= 1


@pytest.mark.asyncio
async def test_get_hss_graph_when_ready(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from backend.graph.store import GraphStore
    from backend.schemas.graph import UnifiedPaperGraph
    from backend.services.paper_service import get_paper_service

    db_path = tmp_path / "scholargraph.db"
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    monkeypatch.setenv("SEED_DEMO_PAPERS", "true")
    reset_persistence_singletons()
    await init_isolated_database(db_path)
    await get_paper_service().bootstrap()

    fixture_path = Path("docs/api/fixtures/graph-hss.json")
    graph_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    graph = UnifiedPaperGraph.model_validate(graph_payload["data"]).model_copy(
        update={"paper_id": "hss-001"},
    )
    GraphStore(base_dir=graph_dir).save(graph)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["paper_id"] == "hss-001"
    assert len(body["data"]["nodes"]) >= 1
