"""B6 HTTP tests: V2 multi-type citation SSE payloads on POST /qa/stream."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from backend.config import get_settings
from backend.llm.client import reset_llm_client_cache
from backend.main import create_app
from backend.rag.hybrid_retriever import HybridRetriever, bind_hybrid_retriever, reset_hybrid_retriever
from backend.rag.models import PaperChunk
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient
from tests.graph.test_qa import _fake_llm
from tests.helpers.persistence_testkit import seed_qa_graph_with_db_async
from tests.rag.test_vector_store import _store

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
V2_FIXTURE = REPO_ROOT / "docs" / "api" / "fixtures" / "qa-stream-v2-frames.json"

_CITATION_REQUIRED: dict[str, set[str]] = {
    "node": {"type", "paper_id", "node_id", "label"},
    "edge": {"type", "paper_id", "edge_id", "label"},
    "chunk": {"type", "paper_id", "chunk_id", "label", "text_preview"},
    "page": {"type", "paper_id", "page", "label"},
}


def _parse_sse_stream(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name = "message"
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((event_name, payload))
    return events


def _assert_citation_matches_openapi(payload: dict[str, Any]) -> None:
    cite_type = payload.get("type")
    assert cite_type in _CITATION_REQUIRED, f"unknown citation type: {cite_type!r}"
    missing = _CITATION_REQUIRED[cite_type] - payload.keys()
    assert not missing, f"{cite_type} citation missing keys: {missing}"
    assert payload["paper_id"]


def _paper_chunk(paper_id: str, chunk_id: str, text: str) -> PaperChunk:
    return PaperChunk(
        chunk_id=chunk_id,
        paper_id=paper_id,
        text=text,
        section="body",
        chunk_index=0,
        source="pymupdf",
        char_start=0,
        char_end=len(text),
    )


@pytest.fixture
async def v2_citation_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """App with graph + in-memory mock vector index wired through app.state."""
    monkeypatch.setenv("QA_RETRIEVAL_TIMEOUT_SECONDS", "3")

    paper_id = "hss-001"
    graph = UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(id="n1", label="核心论点", type="Thesis", data={}),
            GraphNode(id="n2", label="分论点", type="SubArgument", data={}),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source="n2",
                target="n1",
                label="SUB_ARGUMENT_OF",
                type="SUB_ARGUMENT_OF",
            ),
        ],
    )
    await seed_qa_graph_with_db_async(tmp_path, monkeypatch, graph)

    store, _chunk_col, _entity_col, _relation_col, _embedder = _store()
    paper_service = get_paper_service()
    paper_service.set_active_run_id(paper_id, "v2-cite-run")
    await store.index_chunks(
        [
            _paper_chunk(
                paper_id,
                "c1",
                "制度一旦形成便会产生路径依赖，分论点通过机制支撑核心论点。",
            ),
        ],
    )

    retriever = HybridRetriever(vector_store=store)
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_llm_client_cache()

    app = create_app()
    app.state.hybrid_retriever = retriever
    bind_hybrid_retriever(retriever)

    llm_text = "论点[CITE:n1]由关系[CITE:edge:e1]连接，原文[CITE:chunk:c1]有详述，见[CITE:page:12]。"
    monkeypatch.setattr("backend.graph.qa.get_qa_llm_client", lambda: _fake_llm(llm_text))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    reset_hybrid_retriever()
    get_paper_service.cache_clear()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_http_stream_emits_all_v2_citation_types(v2_citation_client: AsyncClient) -> None:
    async with v2_citation_client.stream(
        "POST",
        "/api/v1/papers/hss-001/qa/stream",
        json={"question": "分论点如何支撑核心论点？请引用原文与页码。"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = ""
        async for chunk in response.aiter_text():
            body += chunk

    events = _parse_sse_stream(body)
    citations = [payload for name, payload in events if name == "citation"]
    assert len(citations) >= 4

    for payload in citations:
        _assert_citation_matches_openapi(payload)

    types = {payload["type"] for payload in citations}
    assert types >= {"node", "edge", "chunk", "page"}

    node = next(c for c in citations if c["type"] == "node")
    assert node["node_id"] == "n1"
    assert node["label"] == "核心论点"

    edge = next(c for c in citations if c["type"] == "edge")
    assert edge["edge_id"] == "e1"
    assert "→" in edge["label"]

    chunk = next(c for c in citations if c["type"] == "chunk")
    assert chunk["chunk_id"] == "c1"
    assert chunk["text_preview"]

    page = next(c for c in citations if c["type"] == "page")
    assert page["page"] == 12
    assert "12" in page["label"]

    assert events[-1][0] == "done"


def test_v2_fixture_citation_frames_match_openapi_required_fields() -> None:
    frames = json.loads(V2_FIXTURE.read_text(encoding="utf-8"))
    citation_frames = [frame for frame in frames if frame.get("event") == "citation"]
    assert len(citation_frames) == 4

    for frame in citation_frames:
        _assert_citation_matches_openapi(frame["data"])


def test_openapi_citation_schemas_cover_dispatch_outputs() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    for cite_type, required in _CITATION_REQUIRED.items():
        schema_name = f"QaStreamCitation{cite_type.capitalize()}"
        props = set(schemas[schema_name]["properties"].keys())
        assert required <= props, f"{schema_name} missing {required - props}"
