"""B6 integration: BE SSE citation payloads align with OpenAPI + FE fixture contract."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import yaml
from backend.config import get_settings
from backend.graph.qa_v2 import dispatch_citation
from backend.llm.client import reset_llm_client_cache
from backend.main import create_app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from httpx import ASGITransport, AsyncClient

from tests.graph.test_qa import _fake_llm
from tests.helpers.persistence_testkit import seed_qa_graph_with_db_async

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
V2_FIXTURE = REPO_ROOT / "docs" / "api" / "fixtures" / "qa-stream-v2-frames.json"


def _openapi_citation_variant_names() -> set[str]:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    mapping = spec["components"]["schemas"]["QaStreamCitation"]["discriminator"]["mapping"]
    return set(mapping.keys())


def test_dispatch_citation_variants_match_openapi_discriminator() -> None:
    node_cache = {"n1": "核心论点"}
    edge_cache = {"e1": "分论点 → 核心论点"}
    chunk_cache = {"c1": "制度一旦形成便会产生路径依赖。"}

    samples = [
        dispatch_citation("", "n1", "hss-001", node_cache, edge_cache, chunk_cache),
        dispatch_citation("edge:", "e1", "hss-001", node_cache, edge_cache, chunk_cache),
        dispatch_citation("chunk:", "c1", "hss-001", node_cache, edge_cache, chunk_cache),
        dispatch_citation("page:", "12", "hss-001", node_cache, edge_cache, chunk_cache),
    ]
    openapi_types = _openapi_citation_variant_names()
    emitted = {evt.data["type"] for evt in samples}
    assert emitted == openapi_types


def test_fixture_frame_types_match_openapi_and_dispatch() -> None:
    frames = json.loads(V2_FIXTURE.read_text(encoding="utf-8"))
    cite_types = {frame["data"]["type"] for frame in frames if frame["event"] == "citation"}
    assert cite_types == _openapi_citation_variant_names()


@pytest.fixture
async def graph_only_qa_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    graph_dir = tmp_path / "graphs"
    graph = UnifiedPaperGraph(
        paper_id="hss-001",
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="核心论点", type="Thesis", data={})],
        edges=[],
    )
    await seed_qa_graph_with_db_async(tmp_path, monkeypatch, graph, graph_dir=graph_dir)
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    app = create_app()
    retriever = HybridRetriever(vector_store=None)
    app.state.hybrid_retriever = retriever
    bind_hybrid_retriever(retriever)

    monkeypatch.setattr(
        "backend.graph.qa.get_qa_llm_client",
        lambda: _fake_llm("节点[CITE:n1]是答案。"),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    reset_hybrid_retriever()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mock_route_node_citation_includes_v2_type_field(graph_only_qa_client: AsyncClient) -> None:
    response = await graph_only_qa_client.post(
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "这篇论文的核心论点是什么？"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    citations: list[dict] = []
    event_name = "message"
    for line in response.text.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            if event_name == "citation":
                citations.append(payload)

    assert citations, "expected at least one citation event"
    assert citations[0]["type"] == "node"
    assert citations[0]["node_id"] == "n1"
    assert citations[0]["paper_id"] == "hss-001"
