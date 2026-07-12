#!/usr/bin/env python3
"""Capture a RetrievalContext replay bundle from local graph retrieval (no Chroma/Neo4j).

Usage (repo root)::

    uv run python scripts/capture_retrieval_context_replay.py

Writes ``tests/fixtures/retrieval_context_hss-001-detail.replay.json``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import get_settings
from backend.graph.qa import _GraphQaEngine
from backend.graph.store import GraphStore
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.models import QuestionScale
from backend.rag.retrieval_context_io import build_replay_bundle, dump_replay_bundle, enrich_hss_detail_replay_vectors
from backend.schemas.graph import UnifiedPaperGraph
from backend.services.paper_fixture_seed import seed_from_fixtures
from backend.services.paper_service import PaperService

PAPER_ID = "hss-001"
QUESTION = "分论点如何支撑核心论点？"
OUTPUT_PATH = _REPO_ROOT / "tests" / "fixtures" / "retrieval_context_hss-001-detail.replay.json"
GRAPH_FIXTURE = _REPO_ROOT / "docs" / "api" / "fixtures" / "graph-hss.json"


async def _capture() -> None:
    get_settings.cache_clear()

    graph_payload = json.loads(GRAPH_FIXTURE.read_text(encoding="utf-8"))
    graph = UnifiedPaperGraph.model_validate(graph_payload["data"])
    graph = graph.model_copy(update={"paper_id": PAPER_ID})

    graph_dir = _REPO_ROOT / "data" / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    store = GraphStore(base_dir=graph_dir)
    store.save(graph)

    retriever = HybridRetriever(vector_store=None)
    rc = await retriever.retrieve(
        PAPER_ID,
        QUESTION,
        graph,
        scale=QuestionScale.DETAIL,
    )
    rc = enrich_hss_detail_replay_vectors(rc)

    paper_service = PaperService()
    seed_from_fixtures(paper_service)

    engine = _GraphQaEngine(store=store, paper_service=paper_service)
    events = [evt async for evt in engine.stream(PAPER_ID, QUESTION, retrieval_context=rc)]
    if any(evt.event == "error" for evt in events):
        errors = [evt.data for evt in events if evt.event == "error"]
        raise RuntimeError(f"capture stream failed: {errors}")

    prompt = engine._build_prompt(  # noqa: SLF001 — intentional golden capture
        graph,
        {"nodes": rc.nodes, "edges": rc.edges},
        QUESTION,
        retrieval_context=rc,
    )

    bundle = build_replay_bundle(
        paper_id=PAPER_ID,
        question=QUESTION,
        retrieval_context=rc,
        expected_prompt=prompt,
    )
    dump_replay_bundle(bundle, OUTPUT_PATH)
    print(f"Wrote replay bundle → {OUTPUT_PATH}")
    print(f"prompt_sha256={bundle.expected_prompt_sha256}")


if __name__ == "__main__":
    asyncio.run(_capture())
